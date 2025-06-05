#!/usr/bin/env python3
"""
Orchestrator script for HPE Log Analysis project.
This script coordinates the workflow for a single machine:
1. Process and analyze existing data in the output directory
2. Upload to MongoDB
3. Store results in processed directory
4. Clean up machine-specific directory
"""

import os
import sys
import logging
import subprocess
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

def create_processed_dir():
    """Create a directory for processed results if it doesn't exist"""
    processed_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed")
    os.makedirs(processed_dir, exist_ok=True)
    logging.info(f"Ensuring processed directory exists: {processed_dir}")
    return processed_dir

def run_step(script_name, step_desc, machine_dir=None):
    """Run a python script with proper error handling"""
    logging.info(f"Starting {step_desc}...")
    try:
        # Set up environment variables based on current config
        env = os.environ.copy()
        
        # Set required MongoDB environment variables if not already set
        if "MONGO_DB" not in env:
            env["MONGO_DB"] = "log_analysis_db"
        
        # Get machine name from current environment or use a default
        machine_name = env.get("MONGO_COLLECTION", "unknown_machine")
        
        # Ensure the machine name is used as the collection name
        env["MONGO_COLLECTION"] = machine_name
        
        # Prepare command with optional machine_dir for cleanup step
        command = ["python", script_name]
        if script_name == "3.py" and machine_dir:
            command.append(machine_dir)
        
        # Run the script with the updated environment
        result = subprocess.run(
            command,
            env=env,
            check=True,
            capture_output=True,
            text=True
        )
        
        # Log the output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logging.info(f"{script_name}: {line}")
        
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    logging.warning(f"{script_name} error: {line}")
                    
        logging.info(f"Completed {step_desc}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error in {step_desc}: {e}")
        if e.stdout:
            logging.info(f"Output: {e.stdout}")
        if e.stderr:
            logging.error(f"Error output: {e.stderr}")
        # For step 2 (MongoDB), we want to fail if there's an error
        if script_name == "2.py":
            return False
        # For other steps, we continue even if there are issues
        return True
    except Exception as e:
        logging.error(f"Unexpected error in {step_desc}: {str(e)}")
        # For step 2 (MongoDB), we want to fail if there's an error
        if script_name == "2.py":
            return False
        # For other steps, we continue even if there are issues
        return True


def main():
    """Run the orchestration workflow for a single machine"""
    # Ensure processed directory exists
    processed_dir = create_processed_dir()
    
    # Get machine name from environment
    machine_name = os.environ.get("MONGO_COLLECTION", "unknown_machine")
    machine_dir = os.path.join("output", machine_name)
    
    # Check if machine directory exists
    if not os.path.exists(machine_dir):
        logging.error(f"Machine directory not found: {machine_dir}")
        logging.error("No data to analyze. Aborting workflow.")
        return 1
    
    # Step 1: Process and analyze data (including MongoDB insertion)
    if not run_step("2.py", "processing and analyzing data"):
        logging.error("Failed at data processing/MongoDB step. Aborting workflow.")
        return 1
    
    # Step 3: Clean up machine-specific directory
    if not run_step("3.py", f"cleaning up machine directory {machine_dir}", machine_dir):
        logging.warning(f"Cleanup step had issues for {machine_dir}, but workflow completed.")
        # Cleanup failing is not critical
    
    logging.info("Orchestration workflow completed successfully for this machine.")
    return 0

if __name__ == "__main__":
    sys.exit(main())