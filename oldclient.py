#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import logging
import platform
import time
import re
from datetime import datetime
from pathlib import Path
import traceback
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables for MinIO
load_dotenv()

# Define a fixed bucket name for all machines
MINIO_BUCKET_NAME = "hpe-log-analysis"

# Import shared tasks and success-failure check
try:
    from shared_tasks import prepare_machine as shared_prepare_machine
    from shared_tasks import run_log_extraction as shared_run_log_extraction
    # Import determine_update_type_and_check from success-failure.py
    # Using importlib to handle hyphenated filename
    import importlib.util
    spec = importlib.util.spec_from_file_location("success_failure", "success-failure.py")
    success_failure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(success_failure)
    determine_update_type_and_check = success_failure.determine_update_type_and_check
except ImportError as e:
    logging.error(f"Failed to import modules: {str(e)}. Make sure shared_tasks.py and success-failure.py are in the same directory.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format= 
    '%(asctime)s - %(levelname)s - %(message)s  ',
    handlers=[
        logging.FileHandler("project_run.log"),
        logging.StreamHandler()
    ]
)

# ANSI color codes for terminal output
class Colors:
    HEADER =    '\033[95m'
    BLUE =  '\033[94m'
    CYAN =  '\033[96m'
    GREEN =     '\033[92m'
    YELLOW =    '\033[93m'
    RED =   '\033[91m'
    ENDC =  '\033[0m'
    BOLD =  '\033[1m'
    UNDERLINE =     '\033[4m'

def print_section(title):
    """Print a formatted section title"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{ '=  '*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}=== {title} {Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{   '=  '*80}{Colors.ENDC}\n")

def print_step(step):
    """Print a formatted step description"""
    print(f"{Colors.BLUE}{Colors.BOLD}>> {step}{Colors.ENDC}")

def print_success(message):
    """Print a success message"""
    print(f"{Colors.GREEN}{Colors.BOLD}✓ {message}{Colors.ENDC}")

def print_warning(message):
    """Print a warning message"""
    print(f"{Colors.YELLOW}{Colors.BOLD}⚠ {message}{Colors.ENDC}")

def print_error(message):
    """Print an error message"""
    print(f"{Colors.RED}{Colors.BOLD}✗ {message}{Colors.ENDC}")

def run_command(command, shell=False, check=True, cwd=None, capture_output=True):
    """Run a shell command and return the result, logging output."""
    try:
        command_str = command if isinstance(command, str) else   '   '.join(command)
        logging.info(f"Running command: {command_str} in {cwd or os.getcwd()}")
        print_step(f"Running: {command_str}")
        
        result = subprocess.run(
            command,
            shell=shell,
            check=False, # We check manually to log output before raising
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            cwd=cwd
        )
        
        if capture_output:
            if result.stdout:
                logging.info(f"Command stdout:\n{result.stdout.strip()}")
                # Optionally print stdout too
                # print(result.stdout.strip())
            if result.stderr:
                # Log stderr as warning or error based on return code
                log_level = logging.ERROR if result.returncode != 0 else logging.WARNING
                logging.log(log_level, f"Command stderr:\n{result.stderr.strip()}")
                # Optionally print stderr too
                # print_warning(f"Command stderr:\n{result.stderr.strip()}")

        if check and result.returncode != 0:
            error_msg = f"Command failed with code {result.returncode}: {command_str}"
            if capture_output and result.stderr:
                error_msg += f"\nStderr: {result.stderr.strip()}"
            logging.error(error_msg)
            print_error(error_msg)
            raise subprocess.CalledProcessError(result.returncode, command, output=result.stdout, stderr=result.stderr)
            
        logging.info(f"Command finished with code {result.returncode}: {command_str}")
        return result
        
    except subprocess.CalledProcessError as e:
        # Already logged in the check block if check=True
        if not check:
             print_error(f"Command failed with code {e.returncode}:\n{e.stderr}")
        raise # Re-raise the exception
    except Exception as e:
        error_msg = f"Failed to run command     '{command_str}  ': {str(e)}"
        logging.error(error_msg)
        print_error(error_msg)
        traceback.print_exc()
        raise

def setup_virtual_environment():
    """Set up the Python virtual environment and install dependencies"""
    print_section("Setting up Python Virtual Environment")
    
    venv_dir = Path(".venv")
    requirements_file = Path("requirements.txt")
    
    if not requirements_file.exists():
        print_warning(f"'{requirements_file}' not found. Skipping dependency installation.")
        return True # Not necessarily an error, maybe deps are installed globally
        
    try:
        if venv_dir.exists():
            print_step("Virtual environment already exists. Reusing...")
        else:
            print_step("Creating new virtual environment...")
            run_command([sys.executable, "-m", "venv", ".venv"], check=True)
        
        # Determine the correct pip path based on OS
        if platform.system() == "Windows":
            pip_path = str(venv_dir / "Scripts" / "pip.exe")
            # On Windows, running pip directly often works better than activate+pip
            run_command([pip_path, "install", "-r", str(requirements_file)], check=True)
        else:
            pip_path = str(venv_dir / "bin" / "pip")
            # Use the pip from the venv directly
            run_command([pip_path, "install", "-r", str(requirements_file)], check=True)
        
        print_success("Virtual environment setup complete")
        return True
    except Exception as e:
        print_error(f"Failed to set up virtual environment: {str(e)}")
        return False

def get_minio_client():
    """Get a MinIO client with proper error handling"""
    try:
        client = Minio(
            os.getenv("MINIO_ENDPOINT"),
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=os.getenv("MINIO_SECURE", "True").lower() in ("true", "1", "t"),
        )
        logging.info(f"Successfully connected to MinIO at {os.getenv('MINIO_ENDPOINT')}")
        return client
    except Exception as e:
        logging.error(f"Failed to initialize MinIO client: {str(e)}")
        raise

def sanitize_name(name):
    """
    Sanitize a string to be used as a valid S3 object prefix or bucket name.
    """
    # Convert to lowercase
    name = name.lower()

    # Replace underscores and spaces with hyphens
    name = name.replace("_", "-").replace(" ", "-")

    # Remove any invalid characters (only allow a-z, 0-9, . and -)
    name = re.sub(r"[^a-z0-9.-]", "", name)

    # Replace consecutive hyphens or dots with a single one
    name = re.sub(r"[-]+", "-", name)
    name = re.sub(r"[.]+", ".", name)

    # Remove leading and trailing hyphens and dots
    name = name.strip(".-")

    # Ensure it starts and ends with a letter or number
    if len(name) > 0 and not re.match(r"^[a-z0-9]", name):
        name = "a" + name
    if len(name) > 0 and not re.match(r"[a-z0-9]$", name):
        name = name + "z"

    return name

def upload_to_minio(machine_name, base_output_dir_str="./output"):
    """Upload machine's output (from base_output_dir) to MinIO with error handling."""
    try:
        logging.info(f"Starting MinIO upload for {machine_name}")
        print_step(f"Starting MinIO upload for {machine_name}")

        # Get MinIO client
        client = get_minio_client()

        # Use sanitized machine name as a prefix for organizing files within the bucket
        machine_prefix = sanitize_name(machine_name)
        output_path = os.path.join(base_output_dir_str, machine_name)

        # Ensure the output directory exists (where extracted logs should be)
        if not os.path.isdir(output_path):
            error_msg = f"Output directory not found: {output_path}. Cannot upload. Was log extraction run?"
            logging.error(error_msg)
            print_error(error_msg)
            return False

        logging.info(f"Using prefix '{machine_prefix}' for machine '{machine_name}'")

        # Check if the bucket exists, create if not
        try:
            if not client.bucket_exists(MINIO_BUCKET_NAME):
                client.make_bucket(MINIO_BUCKET_NAME)
                logging.info(f"Created bucket: {MINIO_BUCKET_NAME}")
            else:
                logging.info(f"Using existing bucket: {MINIO_BUCKET_NAME}")
        except Exception as e:
            error_msg = f"Error checking/creating MinIO bucket: {str(e)}"
            logging.error(error_msg)
            print_error(error_msg)
            return False

        # Count files for progress tracking
        total_files = sum(len(files) for _, _, files in os.walk(output_path))
        if total_files == 0:
            warning_msg = f"No files found in {output_path} to upload for {machine_name}."
            logging.warning(warning_msg)
            print_warning(warning_msg)
            return True # Not an error, just nothing to upload
            
        logging.info(f"Found {total_files} files to upload for {machine_name}")
        print_step(f"Found {total_files} files to upload for {machine_name}")

        upload_count = 0
        file_count = 0
        error_count = 0

        # Upload files recursively with error handling
        for root, dirs, files in os.walk(output_path):
            # Process files first
            for file in sorted(files):
                file_count += 1
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, output_path)
                # Create MinIO path with machine prefix
                minio_path = f"{machine_prefix}/{rel_path.replace('\\', '/')}"

                try:
                    # Show progress periodically
                    if file_count % 10 == 0 or file_count == 1 or file_count == total_files:
                        progress_msg = f"Uploading file {file_count}/{total_files} ({file_count/total_files*100:.1f}%): {file}"
                        logging.info(progress_msg)
                        if file_count % 50 == 0 or file_count == 1 or file_count == total_files:
                            print_step(progress_msg)

                    # Upload the file with retry on failure
                    for attempt in range(3):  # Try up to 3 times
                        try:
                            client.fput_object(MINIO_BUCKET_NAME, minio_path, file_path)
                            upload_count += 1
                            break
                        except Exception as e:
                            if attempt < 2:  # Don't log on the last attempt as we'll log after the loop
                                logging.warning(f"Retry {attempt+1}/3 for {file}: {str(e)}")
                                time.sleep(1)  # Small delay before retry
                            else:
                                raise
                except Exception as e:
                    error_msg = f"Failed to upload {file}: {str(e)}"
                    logging.error(error_msg)
                    error_count += 1
                    # Continue with other files

        # Final report
        if upload_count > 0:
            success_rate = (upload_count / total_files) * 100 if total_files > 0 else 0
            result_msg = f"Successfully uploaded {upload_count}/{total_files} files ({success_rate:.1f}%) to MinIO bucket {MINIO_BUCKET_NAME}/{machine_prefix}/"
            logging.info(result_msg)

            # Consider it successful if most files were uploaded
            if success_rate >= 80:
                print_success(result_msg)
                return True
            else:
                warning_msg = f"Upload only partially successful for {machine_name} ({success_rate:.1f}%)"
                logging.warning(warning_msg)
                print_warning(warning_msg)
                return False
        elif total_files > 0: # Only error if there were files to upload
            error_msg = f"No files were successfully uploaded for {machine_name}"
            logging.error(error_msg)
            print_error(error_msg)
            return False
        else: # No files existed, which is fine
            return True

    except Exception as e:
        error_msg = f"Exception in MinIO upload for {machine_name}: {str(e)}"
        logging.error(error_msg)
        print_error(error_msg)
        traceback.print_exc()
        return False

def cleanup_directories(base_source_dir_str="./machines", base_output_dir_str="./output"):
    """Clean up output directories and previously processed data in source dirs"""
    print_section("Cleaning Up Previous Data")
    
    output_dir = Path(base_output_dir_str)
    source_dir = Path(base_source_dir_str)
    
    try:
        # Clean output directory
        if output_dir.exists():
            print_step(f"Removing existing output directory: {output_dir}...")
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        print_success(f"Cleaned and recreated output directory: {output_dir}")
        
        # Clean required_files directories in machine folders
        if source_dir.is_dir():
            print_step(f"Removing existing 'required_files' directories within {source_dir}...")
            count = 0
            for item in source_dir.glob("**/required_files"): # Recursive search
                if item.is_dir():
                    try:
                        shutil.rmtree(item)
                        logging.info(f"Removed directory: {item}")
                        count += 1
                    except Exception as e:
                        print_warning(f"Could not remove {item}: {str(e)}")
            print_success(f"Removed {count} 'required_files' directories.")
        else:
            print_warning(f"Source directory {source_dir} not found, skipping required_files cleanup.")
            
        return True
    except Exception as e:
        print_error(f"Error during cleanup: {str(e)}")
        traceback.print_exc()
        return False

# Removed local definitions of extract_sdmp_file, find_sdmp_files, prepare_machine, run_log_extraction
# These are now imported from shared_tasks.py

def update_machine_status_counts(success_count, failure_count):
    """Update machine update status counts in MongoDB."""
    try:
        # MongoDB connection using credentials from .env
        client = MongoClient(
            host=os.getenv("MONGO_HOST"),
            port=int(os.getenv("MONGO_PORT")),
            username=os.getenv("MONGO_USER"),
            password=os.getenv("MONGO_PASS")
        )
        
        # Get or create database
        db = client[os.getenv("MONGO_DB")]
        
        # Get or create Analytics collection
        analytics_collection = db["Analytics"]
        
        # Get or create the machine status count document
        status_doc = analytics_collection.find_one({"_id": "Machine update status count"})
        
        if status_doc is None:
            # Create new document if it doesn't exist
            analytics_collection.insert_one({
                "_id": "Machine update status count",
                "successful_updates": success_count,
                "failed_updates": failure_count,
                "last_updated": datetime.now()
            })
            logging.info("Created new machine status count document in MongoDB.")
        else:
            # Update existing document
            analytics_collection.update_one(
                {"_id": "Machine update status count"},
                {"$inc": {"successful_updates": success_count, "failed_updates": failure_count}, "$set": {"last_updated": datetime.now()}}
            )
            logging.info("Updated machine status count document in MongoDB.")
        
        print_success("Machine status counts updated in MongoDB.")
        return True
    except Exception as e:
        print_error(f"Failed to update machine status counts in MongoDB: {str(e)}")
        logging.error(f"MongoDB update failed: {str(e)}")
        traceback.print_exc()
        return False

def main():
    print_section("Starting oldclient.py")

    # Define paths
    base_source_dir = "./machines"
    base_output_dir = "./output"
    installsetlog_path = os.path.join(base_output_dir, "installSetLogs.log")
    cidebug_path = os.path.join(base_output_dir, "ciDebug.log")

    # 1. Cleanup previous data
    if not cleanup_directories(base_source_dir, base_output_dir):
        sys.exit(1)

    # 2. Setup virtual environment
    if not setup_virtual_environment():
        sys.exit(1)

    # 3. Prepare machine (dummy for now, replace with actual logic)
    print_section("Preparing Machine")
    try:
        # Assuming shared_prepare_machine takes machine_name and returns a path or success status
        # For this example, let's simulate creating dummy log files
        os.makedirs(base_output_dir, exist_ok=True)
        with open(installsetlog_path, "w") as f:
            f.write('{"update_type": "Offline"}') # Or "Online"
        with open(cidebug_path, "w") as f:
            f.write('fetchFailedComponentList Total number of failed components for server name: xxx, bay yyy uuid: zzz 0\nAbsaroka Firmware update is complete for server: aaa')
        print_success("Dummy log files created for testing.")
    except Exception as e:
        print_error(f"Failed to prepare machine: {str(e)}")
        sys.exit(1)

    # 4. Run log extraction (dummy for now, replace with actual logic)
    print_section("Running Log Extraction")
    try:
        # Assuming shared_run_log_extraction processes logs and puts them in base_output_dir
        print_success("Log extraction simulated.")
    except Exception as e:
        print_error(f"Failed during log extraction: {str(e)}")
        sys.exit(1)

    # 5. Determine update type and check success/failure
    print_section("Checking Firmware Update Status")
    success_condition_met = determine_update_type_and_check(installsetlog_path, cidebug_path)
    
    if success_condition_met:
        print_success("Firmware update check passed.")
        sys.exit(0)
    else:
        print_error("Firmware update check failed.")
        sys.exit(1)

    # 6. Upload to MinIO (optional, can be removed if not needed)
    # print_section("Uploading Logs to MinIO")
    # if not upload_to_minio("test_machine", base_output_dir):
    #     sys.exit(1)

    # 7. Update MongoDB status counts (optional, can be removed if not needed)
    # print_section("Updating MongoDB Status Counts")
    # if success_condition_met:
    #     update_machine_status_counts(1, 0)
    # else:
    #     update_machine_status_counts(0, 1)

    print_section("oldclient.py Finished")

if __name__ == "__main__":
    main()


