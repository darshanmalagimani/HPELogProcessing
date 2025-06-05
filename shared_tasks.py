#!/usr/bin/env python3
# === shared_tasks.py ===
# Contains shared functions for machine preparation and log extraction.

import os
import sys
import subprocess
import shutil
import logging
import tarfile
import platform
import time
from datetime import datetime
from pathlib import Path
import traceback

# Configure logging (can be configured by the calling script)
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )

# ANSI color codes (optional, can be removed if calling script handles printing)
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

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

def run_command(command, shell=False, check=True, cwd=None):
    """Run a shell command and return the result"""
    try:
        print_step(f"Running: {command if isinstance(command, str) else ' '.join(command)}")
        result = subprocess.run(
            command,
            shell=shell,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd
        )
        # Log stdout/stderr instead of printing directly for better integration
        if result.stdout:
            logging.info(f"Command stdout:\n{result.stdout.strip()}")
        if result.stderr:
            # Log stderr as warning, let caller decide if it's an error based on return code
            logging.warning(f"Command stderr:\n{result.stderr.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with code {e.returncode}:\n{e.stderr}")
        raise
    except Exception as e:
        logging.error(f"Failed to run command '{command}': {str(e)}")
        raise

def extract_sdmp_file(sdmp_path):
    """Extract an sdmp file to its directory"""
    logging.info(f"Extracting support dump: {sdmp_path}")
    try:
        parent_dir = sdmp_path.parent
        with tarfile.open(sdmp_path, 'r') as tar_ref:
            tar_ref.extractall(path=parent_dir)
        logging.info(f"Successfully extracted {sdmp_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to extract {sdmp_path}: {str(e)}")
        return False

def find_sdmp_files(machine_dir):
    """Find all .sdmp files in a machine directory"""
    sdmp_files = list(Path(machine_dir).glob("**/*.sdmp"))
    return sdmp_files

def prepare_machine(machine_path_str):
    """Prepare a machine directory by organizing its files"""
    machine_path = Path(machine_path_str)
    logging.info(f"Preparing machine: {machine_path}")
    
    try:
        # Extract SDMP files if present
        sdmp_files = find_sdmp_files(machine_path)
        if sdmp_files:
            logging.info(f"Found {len(sdmp_files)} SDMP file(s) to extract.")
            for sdmp_file in sdmp_files:
                if not extract_sdmp_file(sdmp_file):
                    # Decide if failure to extract one is critical
                    logging.warning(f"Could not extract {sdmp_file}, continuing preparation...")
        else:
            logging.info("No SDMP files found for extraction.")
        
        # Determine the path to use for prepare_machine.py script
        dump_dirs = [d for d in machine_path.glob("*") 
                   if d.is_dir() and not d.name == "required_files"]
        
        sdmp_base_names = [os.path.splitext(os.path.basename(str(f)))[0] for f in sdmp_files]
        matching_dirs = [d for d in dump_dirs if d.name in sdmp_base_names]
        
        target_dir = machine_path
        
        # Run prepare_machine.py script (assuming it's in the same directory or PATH)
        # Ensure prepare_machine.py exists and is executable
        prepare_script = Path("prepare_machine.py") # Adjust path if necessary
        if not prepare_script.exists():
             logging.error(f"'{prepare_script}' not found. Cannot prepare machine.")
             return False
             
        logging.info(f"Running {prepare_script} on target directory: {target_dir}")
        result = run_command([sys.executable, str(prepare_script), str(target_dir)], check=False) # Use sys.executable
        
        if result.returncode == 0:
            logging.info(f"Successfully prepared {machine_path}")
            return True
        else:
            logging.error(f"Failed to prepare {machine_path} (prepare_machine.py returned {result.returncode})")
            return False
    
    except Exception as e:
        logging.error(f"Error preparing machine {machine_path}: {str(e)}")
        traceback.print_exc()
        return False

def run_log_extraction(machine_name, base_source_dir, base_output_dir):
    """Run LogExtraction.py on a prepared machine directory"""
    logging.info(f"Running log extraction for {machine_name}")
    
    try:
        machine_dir = Path(base_source_dir) / machine_name
        
        # Find the required_files directory (assuming it's created by prepare_machine)
        # It might be directly under machine_dir or inside an extracted dump folder
        required_files_path = None
        possible_paths = list(machine_dir.glob("**/required_files"))
        if possible_paths:
             required_files_path = possible_paths[0] # Take the first one found
             logging.info(f"Found required_files directory at: {required_files_path}")
        else:
            logging.error(f"'required_files' directory not found within {machine_dir}")
            return False
        
        # Setup output directory
        output_dir = Path(base_output_dir) / machine_name
        os.makedirs(output_dir, exist_ok=True)
        logging.info(f"Using output directory: {output_dir}")
        
        # Set environment variables and run LogExtraction.py
        # Ensure LogExtraction.py exists and is executable
        log_extraction_script = Path("LogExtraction.py") # Adjust path if necessary
        if not log_extraction_script.exists():
             logging.error(f"'{log_extraction_script}' not found. Cannot run extraction.")
             return False
             
        env = os.environ.copy()
        env["SOURCE_DIR"] = str(required_files_path)
        env["OUTPUT_DIR"] = str(output_dir)
        
        logging.info(f"Running {log_extraction_script} with SOURCE_DIR={required_files_path}, OUTPUT_DIR={output_dir}")
        result = subprocess.run(
            [sys.executable, str(log_extraction_script)], # Use sys.executable
            env=env,
            capture_output=True, # Capture output for logging
            text=True,
            check=False # Check return code manually
        )
        
        # Log output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line:
                    logging.info(f"LogExtraction output: {line}")
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line:
                    # Log stderr as warning or error based on context/return code
                    log_level = logging.ERROR if result.returncode != 0 else logging.WARNING
                    logging.log(log_level, f"LogExtraction stderr: {line}")
        
        if result.returncode == 0:
            logging.info(f"Successfully extracted logs for {machine_name}")
            return True
        else:
            logging.error(f"Log extraction failed for {machine_name} (LogExtraction.py returned {result.returncode})")
            return False
            
    except Exception as e:
        logging.error(f"Error during log extraction for {machine_name}: {str(e)}")
        traceback.print_exc()
        return False

# Example usage (optional, for testing)
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#     # Assume 'machines/machine1' exists and potentially contains sdmp files
#     # Assume prepare_machine.py and LogExtraction.py are in the current directory
#     test_machine_name = "machine1"
#     test_base_source = "./machines"
#     test_base_output = "./output_test"
#     
#     # Create dummy dirs/files if needed for testing
#     Path(test_base_source, test_machine_name).mkdir(parents=True, exist_ok=True)
#     Path(test_base_output).mkdir(exist_ok=True)
#     Path("prepare_machine.py").touch() # Dummy script
#     Path("LogExtraction.py").touch() # Dummy script
#     
#     print("--- Testing prepare_machine ---")
#     prep_success = prepare_machine(str(Path(test_base_source) / test_machine_name))
#     print(f"Preparation success: {prep_success}")
#     
#     # Create dummy required_files if prep succeeded (or manually for testing)
#     if prep_success:
#         Path(test_base_source, test_machine_name, "required_files").mkdir(exist_ok=True)
#         print("--- Testing run_log_extraction ---")
#         extract_success = run_log_extraction(test_machine_name, test_base_source, test_base_output)
#         print(f"Extraction success: {extract_success}")

