#!/usr/bin/env python3
# === master.py ===
# Master orchestrator that analyzes existing log files in the output directory
# and stores JSON results in MongoDB.
# This script only handles analysis - it assumes log files already exist in the output directory.

import os
import sys
import subprocess
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("master_processing.log"), # Use a different log file
        logging.StreamHandler(),
    ],
)

# Load env variables for MongoDB
load_dotenv()

# Set your source base directory (with multiple machine folders)
BASE_OUTPUT_DIR = "./output" # Directory where log files reside


def run_log_analysis(machine_name):
    """Run analysis script (2.py via orchestrator.py) with environment variables"""
    try:
        logging.info(f"Starting log analysis for {machine_name}")

        # Set up environment with variables for the analysis
        env = os.environ.copy()
        env["MONGO_COLLECTION"] = machine_name

        logging.info(
            f"Running analysis with MONGO_COLLECTION={machine_name}"
        )

        # Run the analysis script (ensure orchestrator.py exists)
        analysis_script = Path("orchestrator.py")
        if not analysis_script.exists():
            logging.error(f"Analysis script     '{analysis_script}  ' not found.")
            return False
            
        result = subprocess.run(
            [sys.executable, str(analysis_script)], # Use sys.executable
            env=env,
            capture_output=True,
            text=True,
            check=False # Check return code manually
        )

        # Log output
        if result.stdout:
            for line in result.stdout.strip().split(    '\n '):
                if line:
                    logging.info(f"Analysis output: {line}")
        if result.stderr:
            for line in result.stderr.strip().split(    '\n '):
                if line:
                    log_level = logging.ERROR if result.returncode != 0 else logging.WARNING
                    logging.log(log_level, f"Analysis error: {line}")

        # Check for success and log output
        if result.returncode == 0:
            logging.info(f"Log analysis completed successfully for {machine_name}")
            return True
        else:
            logging.error(
                f"Log analysis failed for {machine_name} with return code {result.returncode}"
            )
            return False

    except Exception as e:
        logging.error(f"Exception during log analysis for {machine_name}: {str(e)}")
        traceback.print_exc()
        return False

# Removed clean_output_folder - master shouldn't clean output as it contains extracted logs
# def clean_output_folder(): ...

def process_machine(machine_name):
    """Process a single machine: Run analysis on existing log files."""
    start_time = datetime.now()
    logging.info(f"\n{'='*80}")
    logging.info(f"=== PROCESSING MACHINE (Analysis): {machine_name} ===")
    logging.info(f"{'='*80}")

    try:
        # Run Analysis
        logging.info(f"\n--- RUNNING ANALYSIS ---")
        step_start = datetime.now()
        analysis_success = run_log_analysis(machine_name)
        step_duration = datetime.now() - step_start

        if not analysis_success:
            logging.error(f"Log analysis failed for {machine_name} after {step_duration}")
            return False
        else:
            logging.info(f"Log analysis completed in {step_duration}")

        # Successfully processed analysis
        total_duration = datetime.now() - start_time
        logging.info(f"\n{'='*80}")
        logging.info(f"✅ SUCCESSFULLY ANALYZED {machine_name}")
        logging.info(f"Total processing time: {total_duration}")
        logging.info(f"{'='*80}")
        return True

    except Exception as e:
        total_duration = datetime.now() - start_time
        logging.error(f"\n{'='*80}")
        logging.error(f"❌ FAILED TO ANALYZE {machine_name}: {str(e)}")
        logging.error(f"Processing time before failure: {total_duration}")
        logging.error(f"{'='*80}")
        traceback.print_exc()
        return False


def main():
    """Main function to analyze all machines found in the output directory."""
    start_time = datetime.now()

    # Display startup banner
    logging.info(f"\n{'#'*80}")
    logging.info(f"# STARTING HPE LOG ANALYSIS MASTER PROCESS")
    logging.info(f"# Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"# Scanning for machine directories in: {BASE_OUTPUT_DIR}")
    logging.info(f"{'#'*80}\n")

    try:
        # No longer cleaning output folder here
        # if not clean_output_folder():
        #     logging.error("Failed to clean output folder, aborting")
        #     return 1

        # Get all machine directories from the OUTPUT directory
        try:
            output_dir_path = Path(BASE_OUTPUT_DIR)
            if not output_dir_path.is_dir():
                logging.error(f"Base output directory '{BASE_OUTPUT_DIR}' not found. Nothing to process.")
                return 1
                
            machine_dirs = [
                d.name
                for d in output_dir_path.iterdir()
                if d.is_dir()
            ]
            if not machine_dirs:
                logging.error(f"No machine directories found in {BASE_OUTPUT_DIR}")
                return 1

            logging.info(
                f"Found {len(machine_dirs)} machines to analyze: {', '.join(machine_dirs)}"
            )
        except Exception as e:
            logging.error(f"Error listing machine directories in output folder: {str(e)}")
            return 1

        # Process each machine
        successful = []
        failed = []

        for i, machine_name in enumerate(sorted(machine_dirs), 1):
            logging.info(
                f"\nAnalyzing machine {i}/{len(machine_dirs)}: {machine_name}"
            )
            # Verify machine directory exists
            machine_path = os.path.join(BASE_OUTPUT_DIR, machine_name)
            if not os.path.isdir(machine_path):
                logging.error(f"Machine directory {machine_path} not found or is not a directory")
                failed.append(machine_name)
                continue

            if process_machine(machine_name):
                successful.append(machine_name)
            else:
                failed.append(machine_name)
                logging.warning(
                    f"Failed to analyze {machine_name}, continuing with next machine"
                )

        # Final summary
        end_time = datetime.now()
        total_duration = end_time - start_time

        logging.info(f"\n{'#'*80}")
        logging.info(f"# ANALYSIS SUMMARY")
        logging.info(f"# Start time:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"# End time:    {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"# Total time:  {total_duration}")
        logging.info(f"# Successful:  {len(successful)}/{len(machine_dirs)}")
        logging.info(f"# Failed:      {len(failed)}/{len(machine_dirs)}")
        logging.info(f"{'#'*80}\n")

        if successful:
            logging.info("Successfully analyzed machines:")
            for i, machine in enumerate(successful, 1):
                logging.info(f"  {i}. {machine}")
        if failed:
            logging.error("Failed to analyze machines:")
            for i, machine in enumerate(failed, 1):
                logging.error(f"  {i}. {machine}")
                
        return 0 if not failed else 1 # Return 0 on success, 1 if any failed

    except Exception as e:
        logging.error(f"Critical error in analysis process: {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)


