#!/usr/bin/env python3
import os
import sys
import shutil
import glob
import argparse
from pathlib import Path

# Files required by LogExtraction.py
REQUIRED_FILES = [
    "version",
    "appliance.properties",
    "ciDebug.log",
    "installSetLogs.log"
]

def find_files(directory, target_files):
    """
    Recursively search for target files in the directory.
    
    Args:
        directory (str): Root directory to search
        target_files (list): List of filenames to search for
        
    Returns:
        dict: Dictionary mapping filename to its full path
    """
    found_files = {}
    
    print(f"Searching for files in: {directory}")
    for root, _, files in os.walk(directory):
        for filename in files:
            if filename in target_files and filename not in found_files:
                found_files[filename] = os.path.join(root, filename)
                print(f"Found {filename} at {found_files[filename]}")
    
    return found_files

def find_serverlogs_dir(directory):
    """
    Find the serverlogs directory or serverlogs-related tar.gz files.
    
    Args:
        directory (str): Root directory to search
        
    Returns:
        dict: Dictionary with 'dir' for serverlogs directory and 'tars' for tar.gz files
    """
    result = {
        'dir': None,
        'tars': []
    }
    
    print(f"Searching for serverlogs directory in: {directory}")
    # First, look for a serverlogs directory
    for root, dirs, _ in os.walk(directory):
        if 'serverlogs' in dirs:
            result['dir'] = os.path.join(root, 'serverlogs')
            print(f"Found serverlogs directory at {result['dir']}")
            break
    
    # Look for .tar.gz files that might contain server logs
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.tar.gz') and ('server' in file.lower() or 'log' in file.lower()):
                result['tars'].append(os.path.join(root, file))
                print(f"Found potential server log archive: {result['tars'][-1]}")
    
    return result

def setup_required_files_dir(machine_dir):
    """
    Create a required_files directory in the machine directory.
    
    Args:
        machine_dir (str): Machine directory path
        
    Returns:
        str: Path to the required_files directory
    """
    required_files_dir = os.path.join(machine_dir, 'required_files')
    os.makedirs(required_files_dir, exist_ok=True)
    
    # Create serverlogs subdirectory
    serverlogs_dir = os.path.join(required_files_dir, 'serverlogs')
    os.makedirs(serverlogs_dir, exist_ok=True)
    
    return required_files_dir

def copy_files(source_files, target_dir):
    """
    Copy files to the target directory.
    
    Args:
        source_files (dict): Dictionary mapping filename to source path
        target_dir (str): Target directory path
        
    Returns:
        list: List of successfully copied files
    """
    copied_files = []
    
    for filename, source_path in source_files.items():
        target_path = os.path.join(target_dir, filename)
        try:
            shutil.copy2(source_path, target_path)
            copied_files.append(filename)
            print(f"Copied {filename} to {target_path}")
        except Exception as e:
            print(f"Failed to copy {filename}: {str(e)}")
    
    return copied_files

def copy_serverlogs(serverlogs_info, target_serverlogs_dir):
    """
    Copy serverlogs directory or tar.gz files to the target directory.
    
    Args:
        serverlogs_info (dict): Dictionary with serverlogs information
        target_serverlogs_dir (str): Target serverlogs directory path
        
    Returns:
        bool: True if successfully copied, False otherwise
    """
    # If we found a serverlogs directory, copy its contents
    if serverlogs_info['dir']:
        try:
            # Copy everything in the serverlogs directory to the target
            for item in os.listdir(serverlogs_info['dir']):
                source_item = os.path.join(serverlogs_info['dir'], item)
                target_item = os.path.join(target_serverlogs_dir, item)
                
                if os.path.isdir(source_item):
                    shutil.copytree(source_item, target_item, dirs_exist_ok=True)
                    print(f"Copied directory {item} to {target_serverlogs_dir}")
                else:
                    shutil.copy2(source_item, target_item)
                    print(f"Copied file {item} to {target_serverlogs_dir}")
            
            return True
        except Exception as e:
            print(f"Failed to copy serverlogs directory: {str(e)}")
            return False
    
    # If we found tar.gz files, copy them to the target serverlogs directory
    elif serverlogs_info['tars']:
        try:
            for tar_file in serverlogs_info['tars']:
                target_file = os.path.join(target_serverlogs_dir, os.path.basename(tar_file))
                shutil.copy2(tar_file, target_file)
                print(f"Copied {os.path.basename(tar_file)} to {target_serverlogs_dir}")
            
            return True
        except Exception as e:
            print(f"Failed to copy serverlogs tar files: {str(e)}")
            return False
    
    print("No serverlogs directory or tar files found.")
    return False

def prepare_machine(machine_dir):
    """
    Prepare a machine directory by organizing its files into the required structure.
    
    Args:
        machine_dir (str): Path to the machine directory
        
    Returns:
        bool: True if successfully prepared, False otherwise
    """
    try:
        print(f"\n=== Preparing machine directory: {machine_dir} ===")
        
        # Ensure the machine directory exists
        if not os.path.exists(machine_dir):
            print(f"Error: Machine directory {machine_dir} does not exist.")
            return False
        
        # Find required files
        found_files = find_files(machine_dir, REQUIRED_FILES)
        print(f"Found {len(found_files)}/{len(REQUIRED_FILES)} required files.")
        
        # Find serverlogs
        serverlogs_info = find_serverlogs_dir(machine_dir)
        
        # Create required_files directory
        required_files_dir = setup_required_files_dir(machine_dir)
        target_serverlogs_dir = os.path.join(required_files_dir, 'serverlogs')
        
        # Copy found files to required_files directory
        copied_files = copy_files(found_files, required_files_dir)
        print(f"Copied {len(copied_files)} files to {required_files_dir}.")
        
        # Copy serverlogs
        serverlogs_copied = copy_serverlogs(serverlogs_info, target_serverlogs_dir)
        
        print(f"\n=== Machine preparation {'successful' if serverlogs_copied else 'partially successful'} ===")
        print(f"Required files directory: {required_files_dir}")
        
        return True
    
    except Exception as e:
        print(f"Error preparing machine directory: {str(e)}")
        return False

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Prepare machine directory for log extraction.')
    parser.add_argument('machine_dir', help='Path to the machine directory')
    
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    
    args = parser.parse_args()
    
    # Prepare the machine directory
    success = prepare_machine(args.machine_dir)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

