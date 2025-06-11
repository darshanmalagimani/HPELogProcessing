import re
import sys

def extract_last_update_type(text):
    """
    Extract the value of the last "update_type" field in the text.
    Returns the value (online or offline) or None if not found.
    """
    search_key = '"update_type":'
    
    try:
        # Find the last occurrence of the search key
        last_pos = text.rindex(search_key)
        
        # Find the position of the first quote after the search key
        start_quote_pos = text.find('"', last_pos + len(search_key))
        
        if start_quote_pos == -1:
            return None  # No opening quote found
        
        # Find the position of the closing quote
        end_quote_pos = text.find('"', start_quote_pos + 1)
        
        if end_quote_pos == -1:
            return None  # No closing quote found
        
        # Extract the value between the quotes
        update_type = text[start_quote_pos + 1:end_quote_pos]
        
        return update_type
    
    except ValueError:
        # If the search key is not found
        return None

def check_firmware_update_status(log_file_path):
    """Checks online firmware update status based on fwInstallState."""
    try:
        with open(log_file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except FileNotFoundError:
        print(f"{log_file_path}: ❌ Error - File not found.")
        return False

    fw_state_pattern = re.compile(r'Updating iLO with fwInstallState:\s*(\w+)', re.IGNORECASE)
    fw_states = [match.group(1) for line in lines if (match := fw_state_pattern.search(line))]
    
    if not fw_states:
        print(f"{log_file_path}: ❌ Failure - Missing 'Updating iLO with fwInstallState:' line.")
        return False

    final_state = fw_states[-1]
    if final_state == "Activated":
        print(f"{log_file_path}: ✅ Success - Firmware update activated.")
        return True
    else:
        print(f"{log_file_path}: ❌ Failure - Final fwInstallState was '{final_state}'.")
        return False

def check_offline_firmware_update(log_file_path):
    """Checks offline firmware update status using two log markers."""
    try:
        with open(log_file_path, 'r', encoding='utf-8') as file:
            log_data = file.read()

        fetch_failed_pattern = re.compile(
            r"fetchFailedComponentList Total number of failed components for server name: .*?, bay .*? uuid: .*? 0"
        )
        absaroka_complete_pattern = re.compile(
            r"Absaroka Firmware update is complete for server:"
        )

        fetch_failed_match = fetch_failed_pattern.search(log_data)
        absaroka_match = absaroka_complete_pattern.search(log_data)

        if fetch_failed_match and absaroka_match:
            print(f"{log_file_path}: ✅ Success - Both offline conditions met.")
            return False
        else:
            print(f"{log_file_path}: ❌ Failure - Offline conditions not met.")
            return False

    except FileNotFoundError:
        print(f"{log_file_path}: ❌ Error - File not found.")
        return False
    except Exception as e:
        print(f"{log_file_path}: ❌ Error - {str(e)}")
        return False

def determine_update_type_and_check(installsetlog, cidebug):
    """
    Main function to classify and verify firmware update.
    """
    try:
        with open(installsetlog, 'r') as file:
            log_data = file.read()

        # Use the extract_last_update_type first
        update_type = extract_last_update_type(log_data)

        if update_type == "Online" or update_type == "online":
            success = check_firmware_update_status(cidebug)
        elif update_type == "Offline" or update_type == "offline":
            success = check_offline_firmware_update(cidebug)
        else:
            print(f"{cidebug}: ⚠️ Could not determine firmware update type.")
            success = False

        return success

    except FileNotFoundError:
        print(f"{cidebug}: ❌ Error - File not found.")
        return False
    except Exception as e:
        print(f"{cidebug}: ❌ Error - {str(e)}")
        return False

# Example usage
if __name__ == "__main__":
    # Test with sample log files
    
    installsetlog = "installSetLogs.log"
    log_file = "ciDebug.log"
    success = determine_update_type_and_check(installsetlog, log_file)
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


