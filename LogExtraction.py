import os
import shutil
import tarfile
import glob
import json
import copy # Import the copy module

# Get configuration from environment variables
SOURCE_DIR = os.getenv("SOURCE_DIR", "")  # Directory containing required files and folders
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "")
REQUIRED_FILES = [
    "version",
    "appliance.properties",
    "ciDebug.log",
    "installSetLogs.log"
    # Add more file names as needed
]
REQUIRED_FOLDERS = [
    "serverlogs"
    # Add more folder names as needed
]

# --- Predefined Empty JSON Structure ---
EMPTY_JSON_STRUCTURE = {
    "OneView": {
        "OV version": "",
        "OV Type": ""
    },
    "Server": {
        "UUID": "",
        "Gen": "",
        "iLO Model": "",
        "OS": "",
        "OsVersion": "",
        "SUT Mode": "",
        "SUT Service State": "",
        "SUT Running Version": ""
    },
    "Firmware Update": {
        "SPP Used": "",
        "Installation Method": "",
        "SUT Mode": "",
        "SUT Service State": "",
        "SUT Running Version": "",
        "Policy": "",
        "Install state": "",
        "Force": ""
    },
    "Install set Response": {
        "SPP": "",
        "Retry": "",
        "Dependency": "",
        "SUM Version": ""
    },
    "Components": [
        {
            "Installed Version": "",
            "To Version": "",
            "DeviceClass": "",
            "TargetGUID": "",
            "FileName": ""
        }
        # Note: This creates a list with one empty component structure.
        # If you need an empty list initially, change this to: "Components": []
    ]
}
# --- End Predefined Structure ---

# --- Updated Function ---
def generate_json_data_for_uuid(uuid_folder_path):
    """
    Returns a deep copy of the predefined empty JSON structure.

    Args:
        uuid_folder_path (str): The path to the specific UUID folder being processed (used for logging).

    Returns:
        dict: A dictionary with the predefined empty structure.
    """
    print(f"Generating empty JSON structure for UUID folder: {os.path.basename(uuid_folder_path)}")
    # Return a deep copy to ensure each JSON file gets a unique dictionary instance
    return copy.deepcopy(EMPTY_JSON_STRUCTURE)
# --- End Updated Function ---

def extract_tar_gz(tar_file, extract_path):
    """
    Extract a .tar.gz file to the specified path.
    
    Args:
        tar_file (str): Path to the .tar.gz file
        extract_path (str): Directory to extract contents to
    """
    try:
        with tarfile.open(tar_file, 'r:gz') as tar_ref:
            tar_ref.extractall(extract_path)
        print(f"Successfully extracted {tar_file} to {extract_path}")
    except Exception as e:
        print(f"Error extracting {tar_file}: {str(e)}")
        raise

def copy_required_items(source_dir, required_files, required_folders, output_dir):
    """
    Copy specified files and folders from source_dir to output_dir,
    and extract .tar.gz files in output_dir/serverlogs.
    
    Args:
        source_dir (str): Directory to search for files/folders
        required_files (list): List of file names to copy
        required_folders (list): List of folder names to copy
        output_dir (str): Destination directory
    """
    try:
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Copy required files and folders
        found_items = {"files": [], "folders": []}
        for root, dirs, files in os.walk(source_dir):
            # Copy specified files
            for file in files:
                if file in required_files:
                    src_path = os.path.join(root, file)
                    dst_path = os.path.join(output_dir, file)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    found_items["files"].append(file)
            
            # Copy specified folders
            for folder in dirs:
                if folder in required_folders:
                    src_path = os.path.join(root, folder)
                    dst_path = os.path.join(output_dir, folder)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                    found_items["folders"].append(folder)
        
        print(f"Copied files: {found_items['files']}")
        print(f"Copied folders: {found_items['folders']}")
        
        # Extract .tar.gz files in output_dir/serverlogs
        serverlogs_dir = os.path.join(output_dir, "serverlogs")
        if os.path.exists(serverlogs_dir):
            tar_files = glob.glob(os.path.join(serverlogs_dir, "*.tar.gz"))
            if tar_files:
                print(f"Found {len(tar_files)} .tar.gz files in {serverlogs_dir}: {tar_files}")
                for tar_file in tar_files:
                    extract_tar_gz(tar_file, serverlogs_dir)
                    # Optionally remove the .tar.gz file after extraction
                    # os.remove(tar_file)
                    # print(f"Removed {tar_file}")
            else:
                print(f"No .tar.gz files found in {serverlogs_dir}")

            # --- Generate JSON for each UUID folder using predefined structure ---
            print(f"Scanning for UUID folders in: {serverlogs_dir}")
            for item in os.listdir(serverlogs_dir):
                item_path = os.path.join(serverlogs_dir, item)
                if os.path.isdir(item_path):
                    print(f"Found potential UUID folder: {item}")
                    uuid_folder_path = item_path
                    try:
                        # Generate the empty structure using the updated function
                        json_data = generate_json_data_for_uuid(uuid_folder_path)
                        
                        # Define the output JSON file path
                        output_json_filename = f"{item}.json"
                        output_json_path = os.path.join(output_dir, output_json_filename)
                        
                        # Write the JSON data to the file
                        with open(output_json_path, 'w') as f_json:
                            json.dump(json_data, f_json, indent=4)
                        print(f"Successfully created JSON file with empty structure: {output_json_path}")
                        
                    except Exception as json_e:
                        print(f"Error generating JSON for {item}: {str(json_e)}")
            # --- End JSON generation logic ---

        else:
            print(f"serverlogs folder not found in copied contents")
                
    except Exception as e:
        print(f"Error during processing: {str(e)}")
        raise

def main():
    try:
        # Verify source directory exists
        if not os.path.exists(SOURCE_DIR):
            raise FileNotFoundError(f"Source directory not found: {SOURCE_DIR}")
        
        copy_required_items(SOURCE_DIR, REQUIRED_FILES, REQUIRED_FOLDERS, OUTPUT_DIR)
        print(f"Successfully copied required items and processed serverlogs .tar.gz files to {OUTPUT_DIR}")
    except Exception as e:
        print(f"Failed to process files: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()