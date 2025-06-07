import os
import json
import re
from pymongo import MongoClient
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

def extract_server_uuid(base_dir):
    """Extract server UUID from the serverlogs directory."""
    try:
        # Define the path to the server logs directory
        serverlogs_dir = os.path.join(base_dir, "serverlogs")
        
        # Check if the directory exists
        if os.path.exists(serverlogs_dir):
            # List all directories in the serverlogs directory (these should be UUIDs)
            uuid_dirs = [d for d in os.listdir(serverlogs_dir) 
                        if os.path.isdir(os.path.join(serverlogs_dir, d))]
            
            if uuid_dirs:
                # Return the first UUID found (you can modify this if there are multiple)
                return uuid_dirs[0]
        
        return None
    except Exception as e:
        print(f"Error extracting server UUID: {e}")
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
    """Extract Install Set Response from second UUID match in the log file and update info_dict."""

    # 1. Look for folder inside the serverlogs_path
    try:
        uuid_dirs = [d for d in os.listdir(serverlogs_path) if os.path.isdir(os.path.join(serverlogs_path, d))]
        if not uuid_dirs:
            raise FileNotFoundError("No UUID folder found inside serverlogs directory.")
        if len(uuid_dirs) > 1:
            raise ValueError("Multiple folders found inside serverlogs; expected only one UUID folder.")

        server_uuid = uuid_dirs[0]
    except Exception as e:
        raise ValueError(f"Error accessing UUID from serverlogs path: {e}")

    print(f"[DEBUG] Extracted UUID from folder: {server_uuid}")
    info_dict["Server"]["UUID"] = server_uuid

    # 2. Read the full log file
    try:
        with open(log_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Log file not found at: {log_path}")

    # 3. Find all positions where the UUID appears
    uuid_positions = [m.start() for m in re.finditer(re.escape(server_uuid), content)]
    print(f"[DEBUG] Found {len(uuid_positions)} matches at: {uuid_positions}")

    if len(uuid_positions) < 2:
        raise ValueError("Second UUID match not found in the log file.")

    # 4. Slice from the second match onward
    second_match_pos = uuid_positions[1]
    content_from_second = content[second_match_pos:]

    # 5. Find the start of JSON after second UUID
    json_start = content_from_second.find('{')
    if json_start == -1:
        raise ValueError("No JSON object found after second UUID.")

    # 6. Extract the full JSON object using brace balancing
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

    # 7. Decode JSON
    try:
        isr_data = json.loads(json_str)
    except json.JSONDecodeError:
        raise ValueError("Failed to decode JSON.")

    # 8. Populate info_dict
    hapi = isr_data.get("hapi", {})

    info_dict["Install set Response"]["SPP"] = hapi.get("install_set", {}).get("Name", "")
    info_dict["Install set Response"]["Retry"] = "No"
    info_dict["Install set Response"]["Dependency"] = ", ".join(hapi.get("dependency_failures", [])) or "None"
    info_dict["Install set Response"]["SUM Version"] = "sum service"
    
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

        # Look for the *last* occurrence of Install State
        for line in reversed(lines):
            if "FirmwareDriverBaselineSettings on server" in line and uuid in line:
                match = re.search(r'FirmwareDriverBaselineSettings on server .*? is (.*)', line)
                if match:
                    install_state = match.group(1).strip()
                    print(f"Install state found: {install_state}")
                    pattern = r'"State"\s*:\s*"([^"]*)"'
                    install_state = re.search(pattern, install_state)
                    install_state = install_state.group(1) if install_state else "Unknown"
                    break

        info_dict["Firmware Update"]["SPP Used"] = spp_used
        # Replace single "SUT" field with three new fields
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
            sut_info["SUT Running Version"] = version_match.group(1).strip()
            
    return sut_info
    
def main():
    # Initialize the dictionary
    info_dict = initialize_dictionary()
    
    # Define the base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Update file paths to match your workspace structure
    version_file_path = os.path.join(base_dir, "version")
    properties_file_path = os.path.join(base_dir, "appliance.properties")
    installset_log_path = os.path.join(base_dir, "installSetLogs.log")
    serverlogs_dir = os.path.join(base_dir, "serverlogs")
    
    # Read and extract version
    version = read_version_file(version_file_path)
    if version:
        info_dict["OneView"]["OV version"] = version
        print(f"OneView version extracted: {version}")
    else:
        print("Failed to extract OneView version")

    # Read and extract MODEL_NUMBER from appliance.properties
    model_number = read_model_number(properties_file_path)
    if model_number:
        info_dict["OneView"]["OV Type"] = model_number
        print(f"OneView type extracted: {model_number}")
    else:
        print("Failed to extract OneView type")

    # Extract server UUID
    server_uuid = extract_server_uuid(base_dir)
    if server_uuid:
        info_dict["Server"]["UUID"] = server_uuid
        print(f"Server UUID extracted: {server_uuid}")
    else:
        print("Failed to extract server UUID")

    # Extract installSetLogs info
    extract_installset_info(installset_log_path, info_dict)
    
    # Call the extract_isr function in the main function
    extract_isr(serverlogs_dir, installset_log_path, info_dict)
    
    # Try to extract firmware log info using UUID (if file exists)
    server_log_path = os.path.join(serverlogs_dir, server_uuid, f"{server_uuid}.log")
    if os.path.exists(server_log_path):
        print(f"Processing server log file: {server_log_path}")
        extract_firmware_log_info(server_log_path, server_uuid, info_dict)
    else:
        print(f"Server log file not found: {server_log_path}")
        
        # Try to extract SUT info from uuid.log if it exists
        uuid_log_path = os.path.join(serverlogs_dir, server_uuid, "uuid.log")
        if os.path.exists(uuid_log_path):
            try:
                with open(uuid_log_path, 'r') as file:
                    uuid_log_content = file.read()
                    # Use the extract_sut_info function from test.py if available
                    # Otherwise extract it manually
                    sut_info = extract_sut_info_from_log_content(uuid_log_content, server_uuid) if 'extract_sut_info_from_log_content' in globals() else {}
                    
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
    extract_ilo_model(installset_log_path, info_dict)

    # Process dependency failure JSON
    dependency_path = os.path.join(serverlogs_dir, server_uuid, "DependencyFailure.json")
    if os.path.exists(dependency_path):
        print(f"Processing dependency file: {dependency_path}")
        process_dependency_failure_json(dependency_path, info_dict)
    else:
        print(f"No DependencyFailure.json found at: {dependency_path}")
        
    # Output the updated dictionary
    print("\nUpdated Dictionary:")
    print(json.dumps(info_dict, indent=4))

    # Insert the dictionary into MongoDB

    load_dotenv()
    mongo_user = quote_plus(os.getenv("MONGO_USER"))
    mongo_pass = quote_plus(os.getenv("MONGO_PASS"))
    mongo_host = os.getenv("MONGO_HOST", "localhost")
    mongo_port = os.getenv("MONGO_PORT", "27017")
    mongo_db_name = os.getenv("MONGO_DB", "log_analysis_db")
    mongo_collection_name = os.getenv("MONGO_COLLECTION", "extracted_info")

    # Construct connection string
    mongo_uri = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"

    try:
        client = MongoClient(mongo_uri)
        db = client["log_analysis_db"]
        collection = db["extracted_info"]
        insert_result = collection.insert_one(info_dict)
        print(f"\nDictionary inserted into MongoDB with ID: {insert_result.inserted_id}")
    except Exception as e:
        print(f"Error inserting into MongoDB: {e}")



if __name__ == "__main__":
    main()
