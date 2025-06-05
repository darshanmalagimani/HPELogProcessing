import os
import shutil
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Define protected directories and files that should never be deleted
PROTECTED_DIRS = [
    "machines",       # Source machine data
    ".venv",          # Virtual environment
    ".git",           # Git repository if present
    "__pycache__"     # Python cache
]

PROTECTED_FILES = [
    ".env",           # Environment variables
    "requirements.txt", # Python requirements
    "run_project.py", # Main project script
    "master.py",      # Master processing script
    "LogExtraction.py", # Log extraction script
    "prepare_machine.py", # Machine preparation script
    "orchestrator.py",  # Orchestrator script
    "1.py",           # Script 1
    "2.py",           # Script 2
    "3.py",           # This script
    "processing.log",  # Log file
    "project_run.log"  # Project run log
]

def safe_cleanup(machine_dir=None):
    """
    Safely clean up the specified machine directory while preserving source data.
    If machine_dir is provided, only that directory is cleaned. Otherwise, no cleanup is performed.

    Args:
        machine_dir (str, optional): Path to the machine-specific directory to clean.
    """
    if not machine_dir:
        print("No machine directory specified for cleanup. Skipping cleanup.")
        return

    print(f"Starting safe cleanup process for machine directory: {machine_dir}")

    # Clean up the specified machine directory if it exists
    if os.path.exists(machine_dir) and os.path.isdir(machine_dir):
        # Verify that the directory is within the output directory to prevent accidental deletion
        output_base = os.path.abspath("./output")
        machine_path = os.path.abspath(machine_dir)
        if not machine_path.startswith(output_base):
            print(f"Error: Machine directory {machine_dir} is not within {output_base}. Skipping cleanup for safety.")
            return

        print(f"Cleaning machine directory: {machine_dir}")
        try:
            shutil.rmtree(machine_dir)
            print(f"Deleted machine directory: {machine_dir}")
        except Exception as e:
            print(f"Could not delete machine directory {machine_dir}: {e}")
    else:
        print(f"Machine directory not found: {machine_dir}")

    print("Cleanup complete.")

if __name__ == "__main__":
    # Check for command-line argument specifying the machine directory
    machine_dir = sys.argv[1] if len(sys.argv) > 1 else None
    safe_cleanup(machine_dir)