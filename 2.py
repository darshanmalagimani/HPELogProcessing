import os
import json
import re
import time
import shutil
import glob
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from dotenv import load_dotenv
from urllib.parse import quote_plus

def initialize_dictionary():
    """Initialize the dictionary structure to store all information."""
    return {
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
        "Components": []
    }

def read_version_file(file_path):
    """Read and extract version from the specified file."""
    try:
        with open(file_path, 'r') as file:
            content = file.read().strip()
            return content
    except Exception as e:
        print(f"Error reading version file: {e}")
        return None

def read_model_number(file_path):
    """Read and extract MODEL_NUMBER from the appliance.properties file."""
    try:
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if line.startswith("MODEL_NUMBER ="):
                    model_number = line.split("=", 1)[1].strip()
                    return model_number
        return None
    except Exception as e:
        print(f"Error reading appliance.properties file: {e}")
        return None

def extract_ilo_model(file_path, info_dict):
    """Extract iLO model and OS information from installSetLogs.log file."""
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if "Request = " in line:
                    # Extract the JSON string from after "Request = " to the end of line
                    json_str = line.split("Request = ", 1)[1].strip()
                    try:
                        # Parse the JSON string
                        request_data = json.loads(json_str)
                        
                        # Extract OS information
                        host_os = request_data.get("hapi", {}).get("HostOS", {})
                        if host_os:
                            os_name = host_os.get("OsName", "")
                            os_version = host_os.get("OsVersion", "")
                            if os_name:
                                info_dict["Server"]["OS"] = os_name
                                info_dict["Server"]["OsVersion"] = os_version
                                print(f"OS Name extracted: {os_name}")
                                print(f"OS Version extracted: {os_version}")
                        
                        # Navigate to fw_inventory array
                        fw_inventory = request_data.get("hapi", {}).get("server_inventory", {}).get("fw_inventory", [])
                        
                        # Find the first item with "Id": "1"
                        for item in fw_inventory:
                            if item.get("Id") == "1":
                                ilo_model = item.get("Name", "")
                                if ilo_model:
                                    info_dict["Server"]["iLO Model"] = ilo_model
                                    
                                    # Map iLO model to server generation
                                    if "iLO 5" in ilo_model:
                                        info_dict["Server"]["Gen"] = "Gen10"
                                    elif "iLO 6" in ilo_model:
                                        info_dict["Server"]["Gen"] = "Gen11"
                                    elif "iLO 7" in ilo_model:
                                        info_dict["Server"]["Gen"] = "Gen12"
                                        
                                    print(f"iLO model extracted: {ilo_model}")
                                    print(f"Server generation determined: {info_dict['Server']['Gen']}")
                                    
                        # If we've reached here, we've processed the JSON regardless of whether we found everything
                        return True
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON from installSetLogs.log: {e}")
                        continue
        
        print("Failed to extract information: No matching data found")
        return False
    
    except Exception as e:
        print(f"Error extracting information from log: {e}")
        return False

def extract_isr(serverlogs_path: str, log_path: str, info_dict: dict):
    """Extract Install Set Response from log file and update info_dict."""
    try:
        # Get already extracted UUID from info_dict
        server_uuid = info_dict.get("Server", {}).get("UUID")
        if not server_uuid:
            raise ValueError("Server UUID not found in info_dict")
            
        # Verify that the UUID folder exists in serverlogs
        uuid_folder_path = os.path.join(serverlogs_path, server_uuid)
        if not os.path.isdir(uuid_folder_path):
            raise ValueError(f"UUID folder {server_uuid} not found in serverlogs directory")
            
        print(f"[DEBUG] Using UUID folder: {server_uuid}")
        
        # Read the full log file
        try:
            with open(log_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Log file not found at: {log_path}")

        # Find all positions where the UUID appears
        uuid_positions = [m.start() for m in re.finditer(re.escape(server_uuid), content)]
        print(f"[DEBUG] Found {len(uuid_positions)} matches at: {uuid_positions}")

        if len(uuid_positions) < 2:
            raise ValueError("Second UUID match not found in the log file.")

        # Slice from the second match onward
        second_match_pos = uuid_positions[1]
        content_from_second = content[second_match_pos:]

        # Find the start of JSON after second UUID
        json_start = content_from_second.find('{')
        if json_start == -1:
            raise ValueError("No JSON object found after second UUID.")

        # Extract the full JSON object using brace balancing
        json_str = ''
        brace_count = 0
        for char in content_from_second[json_start:]:
            json_str += char
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    break

        # Decode JSON
        try:
            isr_data = json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError("Failed to decode JSON.")

        # Populate info_dict
        hapi = isr_data.get("hapi", {})

        info_dict["Install set Response"]["SPP"] = hapi.get("install_set", {}).get("Name", "")
        info_dict["Install set Response"]["Retry"] = "No"
        info_dict["Install set Response"]["Dependency"] = ", ".join(hapi.get("dependency_failures", [])) or "None"
        info_dict["Install set Response"]["SUM Version"] = "sum service"
        
    except Exception as e:
        print(f"Error in extract_isr: {str(e)}")
        raise
    
def extract_installset_info(file_path, info_dict):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
            # Installation Method
            install_method_match = re.search(r'"update_type"\s*:\s*"([^"]+)"', content)
            if install_method_match:
                info_dict["Firmware Update"]["Installation Method"] = install_method_match.group(1)

            # Force
            force_match = re.search(r'"rewrite"\s*:\s*(true|false)', content)
            if force_match:
                info_dict["Firmware Update"]["Force"] = force_match.group(1).capitalize()

            # Policy
            downgrade_match = re.search(r'"downgrade"\s*:\s*(true|false)', content)
            if downgrade_match:
                policy = "Exact Match" if downgrade_match.group(1) == "true" else "LowerThanBaseline"
                info_dict["Firmware Update"]["Policy"] = policy

    except Exception as e:
        print(f"Error reading installSetLogs.log: {e}")

def extract_firmware_log_info(log_path, uuid, info_dict):
    try:
        with open(log_path, 'r') as file:
            lines = file.readlines()

        spp_used = ""
        sut_mode = ""
        sut_service_state = ""
        sut_running_version = ""
        install_state = ""

        for line in lines:
            if "The selected baseline" in line and "is absaroka compliant = true" in line:
                match = re.search(r'The selected baseline (.*?) is absaroka compliant = true', line)
                if match:
                    spp_used = match.group(1)
            
            # Extract SUT information from the log
            if f"Successfully got SUT status from server via RIS for {uuid}" in line:
                # Extract information from the line that looks like:
                # [Mode: AutoStageService State: DisabledVersion: 5.2.0.0Type: #SUT.v5_2_0.SUT...]
                # Find the section between square brackets
                match = re.search(r'\[(.*?)\]', line)
                if match:
                    section = match.group(1)
                    
                    # Extract Mode
                    mode_match = re.search(r'Mode: (.*?)Service', section)
                    if mode_match:
                        sut_mode = mode_match.group(1).strip()
                    
                    # Extract State
                    state_match = re.search(r'State: ([^V]*?)Version:', section)
                    if state_match:
                        sut_service_state = state_match.group(1).strip()
                    
                    # Extract Version
                    version_match = re.search(r'Version: ([^T]*?)Type:', section)
                    if version_match:
                        sut_running_version = version_match.group(1).strip()

        # Look for the last occurrence of Install State
        for line in reversed(lines):
            if "FirmwareDriverBaselineSettings on server" in line and uuid in line:
                match = re.search(r'FirmwareDriverBaselineSettings on server .*? is (.*)', line)
                if match:
                    install_state = match.group(1).strip()
                    # print(f"Install state found: {install_state}")
                    pattern = r'"State"\s*:\s*"([^"]*)"'
                    install_state = re.search(pattern, install_state)
                    install_state = install_state.group(1) if install_state else "Unknown"
                    break

        info_dict["Firmware Update"]["SPP Used"] = spp_used
        info_dict["Firmware Update"]["SUT Mode"] = sut_mode
        info_dict["Firmware Update"]["SUT Service State"] = sut_service_state
        info_dict["Firmware Update"]["SUT Running Version"] = sut_running_version
        info_dict["Server"]["SUT Mode"] = sut_mode
        info_dict["Server"]["SUT Service State"] = sut_service_state
        info_dict["Server"]["SUT Running Version"] = sut_running_version
        info_dict["Firmware Update"]["Install state"] = install_state

    except Exception as e:
        print(f"Error reading firmware update log file: {e}")

def process_dependency_failure_json(file_path, info_dict):
    """Process DependencyFailure.json to extract component information."""
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
            
        # Extract Install set Response information
        if "install_set" in data:
            if "Name" in data["install_set"]:
                info_dict["Install set Response"]["SPP"] = data["install_set"]["Name"]
            if "Description" in data["install_set"]:
                info_dict["Install set Response"]["Dependency"] = data["install_set"]["Description"]
        
        # Clear existing components to ensure only this UUID's components are included
        info_dict["Components"] = []
        
        # Extract Component information
        if "sequence_details" in data:
            for component in data["sequence_details"]:
                component_dict = {
                    "Installed Version": "",
                    "To Version": "",
                    "DeviceClass": "",
                    "TargetGUID": "",
                    "FileName": ""
                }
                
                # Fill in component details
                if "PackageVersion" in component:
                    component_dict["To Version"] = component["PackageVersion"]
                if "Filename" in component:
                    component_dict["FileName"] = component["Filename"]
                
                # Extract installed version and target GUID
                if "InstalledVersion" in component and component["InstalledVersion"]:
                    for installed_ver in component["InstalledVersion"]:
                        if "Version" in installed_ver:
                            component_dict["Installed Version"] = installed_ver["Version"]
                        if "Target" in installed_ver:
                            component_dict["TargetGUID"] = installed_ver["Target"]
                
                # Add component to the list
                info_dict["Components"].append(component_dict)
                
                print(f"Added component: {component_dict['FileName']}")
        
        return True
    except Exception as e:
        print(f"Error processing DependencyFailure.json: {e}")
        return False

def find_dependency_failure_json_files(serverlogs_dir):
    """Find all DependencyFailure.json files in the serverlogs directory and its subdirectories."""
    dependency_files = []
    
    # Walk through all subdirectories in serverlogs_dir
    for root, dirs, files in os.walk(serverlogs_dir):
        # Check if DependencyFailure.json exists in this directory
        if "DependencyFailure.json" in files:
            dependency_files.append(os.path.join(root, "DependencyFailure.json"))
    
    return dependency_files

def extract_sut_info_from_log_content(log_content, uuid):
    """Extract SUT information directly from log content."""
    sut_info = {
        "SUT Mode": "Not Available",
        "SUT Service State": "Not Available",
        "SUT Running Version": "Not Available"
    }
    
    # Look for the SUT status line
    pattern = rf"Successfully got SUT status from server via RIS for {uuid}, \[(.*?)\]"
    matches = re.findall(pattern, log_content)
    
    if matches:
        sut_section = matches[0]
        print(f"Found SUT status section: {sut_section}")
        
        # Extract Mode
        mode_match = re.search(r'Mode: ([^S]*?)State:', sut_section)
        if mode_match:
            sut_info["SUT Mode"] = mode_match.group(1).strip()
            
        # Extract State
        state_match = re.search(r'State: ([^V]*?)Version:', sut_section)
        if state_match:
            sut_info["SUT Service State"] = state_match.group(1).strip()
            
        # Extract Version
        version_match = re.search(r'Version: ([^T]*?)Type:', sut_section)
        if version_match:
            sut_info["SUT Running Version"] = mode_match.group(1).strip()
            
    return sut_info
    
def connect_to_mongodb(max_retries=3, retry_delay=2):
    """Connect to MongoDB with retry logic"""
    load_dotenv()
    mongo_user = quote_plus(os.getenv("MONGO_USER"))
    mongo_pass = quote_plus(os.getenv("MONGO_PASS"))
    mongo_host = os.getenv("MONGO_HOST", "localhost")
    mongo_port = os.getenv("MONGO_PORT", "27017")
    mongo_db_name = os.getenv("MONGO_DB", "log_analysis_db")
    
    # Construct connection string
    mongo_uri = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"
    
    for attempt in range(max_retries):
        try:
            print(f"Connecting to MongoDB at {mongo_host}:{mongo_port} (attempt {attempt+1}/{max_retries})...")
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            # Force a connection to verify it works
            client.admin.command('ismaster')
            print("Successfully connected to MongoDB")
            
            # Test database access
            db = client[mongo_db_name]
            print(f"Successfully accessed database: {mongo_db_name}")
            
            # List available collections
            collections = db.list_collection_names()
            print(f"Available collections: {collections}")
            
            return client, mongo_db_name
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            if attempt < max_retries - 1:
                print(f"MongoDB connection failed: {str(e)}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"Failed to connect to MongoDB after {max_retries} attempts: {str(e)}")
                raise
        except Exception as e:
            print(f"Unexpected error connecting to MongoDB: {str(e)}")
            raise

def create_processed_directory():
    """Create a directory for processed machine data"""
    processed_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed")
    os.makedirs(processed_dir, exist_ok=True)
    print(f"Created/verified processed directory: {processed_dir}")
    return processed_dir

def main():
    # Get the machine name from environment variable
    machine_name = os.getenv("MONGO_COLLECTION", "unknown_machine")
    
    # Define the base directory structure
    output_base_dir = os.path.join("output", machine_name)
    output_dir = os.path.join(output_base_dir, machine_name)  # Files are in this nested directory
    
    if not os.path.exists(output_dir):
        print(f"Output directory not found: {output_dir}")
        print("Checking alternative path...")
        output_dir = output_base_dir
        if not os.path.exists(output_dir):
            print(f"Alternative output directory not found: {output_dir}")
            return
    
    # Create processed directory
    processed_dir = create_processed_directory()

    # Update file paths to use the output directory
    version_file_path = os.path.join(output_dir, "version")
    properties_file_path = os.path.join(output_dir, "appliance.properties")
    installset_log_path = os.path.join(output_dir, "installSetLogs.log")
    serverlogs_dir = os.path.join(output_dir, "serverlogs")
    
    print(f"\nProcessing files in directory: {output_dir}")
    print(f"Using paths:")
    print(f"  Version file: {version_file_path}")
    print(f"  Properties file: {properties_file_path}")
    print(f"  Install set log: {installset_log_path}")
    print(f"  Server logs dir: {serverlogs_dir}")
    
    # Read shared information once
    version = read_version_file(version_file_path) if os.path.exists(version_file_path) else None
    model_number = read_model_number(properties_file_path) if os.path.exists(properties_file_path) else None
    
    # Find all JSON files in the output directory that match UUID pattern
    json_files = glob.glob(os.path.join(output_dir, "*.json"))
    uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\.json$')
    json_files = [f for f in json_files if uuid_pattern.match(os.path.basename(f))]
    
    if not json_files:
        print(f"No UUID JSON files found in {output_dir}")
        return
    
    print(f"Found {len(json_files)} JSON files: {[os.path.basename(f) for f in json_files]}")
    
    # Connect to MongoDB once
    try:
        client, mongo_db_name = connect_to_mongodb(max_retries=3, retry_delay=2)
        mongo_collection_name = os.getenv("MONGO_COLLECTION", "extracted_info")
        db = client[mongo_db_name]
        collection = db[mongo_collection_name]
        print(f"Using collection: {mongo_collection_name}")
    except Exception as e:
        print(f"Failed to connect to MongoDB: {str(e)}")
        return
    
    # Process each JSON file
    for json_file in json_files:
        uuid = os.path.splitext(os.path.basename(json_file))[0]
        print(f"\n=== Processing JSON file for UUID: {uuid} ===")
        
        # Create a new dictionary for each JSON file
        info_dict = initialize_dictionary()
        
        # Load the JSON file's contents and merge into the new dictionary
        try:
            with open(json_file, 'r') as f:
                json_data = json.load(f)
            info_dict.update(json_data)
        except Exception as e:
            print(f"Error loading JSON file {json_file}: {e}")
            continue
        
        # Update shared fields
        if version:
            info_dict["OneView"]["OV version"] = version
            print(f"OneView version extracted: {version}")
        else:
            print("Failed to extract OneView version")
        
        if model_number:
            info_dict["OneView"]["OV Type"] = model_number
            print(f"OneView type extracted: {model_number}")
        else:
            print("Failed to extract OneView type")
        
        # Set UUID
        info_dict["Server"]["UUID"] = uuid
        print(f"Server UUID set: {uuid}")
        
        # Extract installSetLogs info
        if os.path.exists(installset_log_path):
            extract_installset_info(installset_log_path, info_dict)
        else:
            print(f"Install set log file not found: {installset_log_path}")
        
        # Extract ISR for this UUID
        if os.path.exists(serverlogs_dir) and os.path.exists(installset_log_path):
            try:
                extract_isr(serverlogs_dir, installset_log_path, info_dict)
            except Exception as e:
                print(f"Failed to extract ISR for UUID {uuid}: {e}")
        
        # Try to extract firmware log info using UUID
        server_log_path = os.path.join(serverlogs_dir, uuid, f"{uuid}.log")
        if os.path.exists(server_log_path):
            print(f"Processing server log file: {server_log_path}")
            extract_firmware_log_info(server_log_path, uuid, info_dict)
        else:
            print(f"Server log file not found: {server_log_path}")
            
            # Try to extract SUT info from uuid.log if it exists
            uuid_log_path = os.path.join(serverlogs_dir, uuid, "uuid.log")
            if os.path.exists(uuid_log_path):
                try:
                    with open(uuid_log_path, 'r') as file:
                        uuid_log_content = file.read()
                        sut_info = extract_sut_info_from_log_content(uuid_log_content, uuid)
                        
                        if sut_info:
                            info_dict["Server"]["SUT Mode"] = sut_info.get("SUT Mode", "")
                            info_dict["Server"]["SUT Service State"] = sut_info.get("SUT Service State", "")
                            info_dict["Server"]["SUT Running Version"] = sut_info.get("SUT Running Version", "")
                            info_dict["Firmware Update"]["SUT Mode"] = sut_info.get("SUT Mode", "")
                            info_dict["Firmware Update"]["SUT Service State"] = sut_info.get("SUT Service State", "")
                            info_dict["Firmware Update"]["SUT Running Version"] = sut_info.get("SUT Running Version", "")
                except Exception as e:
                    print(f"Error processing uuid.log: {e}")
        
        # Try to extract iLO model
        if os.path.exists(installset_log_path):
            extract_ilo_model(installset_log_path, info_dict)
        
        # Process dependency failure JSON for this UUID
        dependency_path = os.path.join(serverlogs_dir, uuid, "DependencyFailure.json")
        if os.path.exists(dependency_path):
            print(f"Processing dependency file: {dependency_path}")
            process_dependency_failure_json(dependency_path, info_dict)
        else:
            print(f"No DependencyFailure.json found at: {dependency_path}")
        
        # Output the updated dictionary
        print(f"\nUpdated Dictionary for UUID {uuid}:")
        print(json.dumps(info_dict, indent=4))
        
        # Save the dictionary as JSON in the processed directory
        machine_json_path = os.path.join(processed_dir, f"{machine_name}_{uuid}_analysis.json")
        try:
            with open(machine_json_path, 'w') as f:
                json.dump(info_dict, f, indent=4)
            print(f"Saved analysis results to {machine_json_path}")
        except Exception as e:
            print(f"Error saving JSON file: {e}")
        
        # Insert the dictionary into MongoDB
        try:
            print(f"\n=== MONGODB UPDATE PROCESS for UUID {uuid} ===")
            print(f"Machine: {machine_name}")
            print(f"Data to insert: {json.dumps(info_dict, indent=2)}")
            
            # Insert the document
            print(f"Inserting document into collection '{mongo_collection_name}'...")
            insert_result = collection.insert_one(info_dict)
            
            if insert_result.acknowledged:
                print(f"MongoDB insert successful! Document ID: {insert_result.inserted_id}")
                
                # Verify the insertion by reading back the document
                inserted_doc = collection.find_one({"_id": insert_result.inserted_id})
                if inserted_doc:
                    print(f"Successfully verified document in MongoDB for UUID {uuid}")
                else:
                    raise Exception(f"Document was inserted but could not be read back for UUID {uuid}")
            else:
                raise Exception(f"Insert operation was not acknowledged by MongoDB for UUID {uuid}")
                
        except Exception as e:
            print(f"\n!!! ERROR INSERTING INTO MONGODB for UUID {uuid} !!!")
            print(f"Error details: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            print("Stack trace:")
            import traceback
            traceback.print_exc()
            print(f"\nData analysis completed but MongoDB storage failed for UUID {uuid}.")
            print(f"Results are still available in the JSON file: {machine_json_path}")
            continue  # Continue with next JSON file
    
    # Close the MongoDB connection
    try:
        client.close()
        print("MongoDB connection closed")
        print("=== MONGODB UPDATE COMPLETE ===")
    except Exception as e:
        print(f"Error closing MongoDB connection: {e}")
    
    # Move the machine directory to processed directory
    prefix = os.getenv("BUCKET_PREFIX", "")
    if prefix and os.path.exists(prefix):
        try:
            dest_path = os.path.join(processed_dir, prefix)
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.move(prefix, dest_path)
            print(f"Moved {prefix} directory to {dest_path}")
        except Exception as e:
            print(f"Error moving {prefix} directory: {e}")

if __name__ == "__main__":
    main()
