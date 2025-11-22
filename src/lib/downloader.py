# lib/downloader.py
#
# Implements OTA update functionality by downloading files listed in a
# 'update_manifest.json' directly to their final destination.
#
# Optimized for RAM usage on Raspberry Pi Pico W.
#
# Author: Simon Klenk 2025
# License: MIT
#
import gc
import os
import machine
import ujson as json

# --- Configuration ---
# Optional: Set token if repo is private
GITHUB_TOKEN = "" 
REPO_OWNER = 'Simon-Klenk'
REPO_NAME = 'AV_Notification_System'
BRANCH = 'main'

def ensure_dir_exists(filepath):
    """
    Ensures that the directory structure for the given file path exists.
    Example: for 'lib/utils/helpers.py', it creates 'lib' and 'lib/utils'.
    """
    # Remove filename, keep folder path
    folder_path = "/".join(filepath.split("/")[:-1])
    
    if folder_path:
        parts = folder_path.split("/")
        current_path = ""
        for p in parts:
            if p:
                current_path += p + "/"
                # Remove trailing slash for stat check
                check_path = current_path[:-1]
                try:
                    os.stat(check_path)
                except OSError:
                    try:
                        os.mkdir(check_path)
                        print(f"Created directory: {check_path}")
                    except Exception as e:
                        print(f"Error creating directory {check_path}: {e}")
        gc.collect()

def _http_request_stream(url, headers=None):
    """
    Opens a generic HTTPS connection and returns the socket stream and status code.
    Imports ssl/socket locally to save global RAM.
    """
    # Local imports to save RAM when module is loaded but not used
    import usocket
    import ssl
    
    s = None
    try:
        if url.startswith("https://"):
            url_parts = url[len("https://"):].split("/", 1)
            host = url_parts[0]
            path = "/" + url_parts[1] if len(url_parts) > 1 else "/"
        else:
            print("Error: Only HTTPS supported")
            return None, 0

        addr = usocket.getaddrinfo(host, 443)[0][-1]
        
        s = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        s.settimeout(15) # Slightly increased timeout
        s.connect(addr)
        
        gc.collect() 
        
        # SNI (Server Name Indication) is often required by GitHub
        s = ssl.wrap_socket(s, server_hostname=host)

        request_lines = [
            "GET {} HTTP/1.0".format(path),
            "Host: {}".format(host),
        ]
        if headers:
            for key, value in headers.items():
                request_lines.append("{}: {}".format(key, value))
        request_lines.append("\r\n")
        s.write("\r\n".join(request_lines).encode('utf-8'))

        # Read status line
        status_line = s.readline().decode('utf-8').strip()
        parts = status_line.split(' ')
        status_code = int(parts[1]) if len(parts) > 1 else 0

        # Skip headers
        while True:
            line = s.readline()
            if not line or line == b"\r\n":
                break
        
        return s, status_code
    except Exception as e:
        print(f"Error in connection: {e}")
        if s: s.close()
        return None, 0

def download_file_blob(url, local_filename, headers=None):
    """
    Downloads a file stream directly to the target path.
    """
    ensure_dir_exists(local_filename)
    
    s = None
    try:
        gc.collect()
        s, status_code = _http_request_stream(url, headers=headers)
        
        if status_code != 200:
            print(f"HTTP Error {status_code} for {local_filename}")
            if s: s.close()
            return False

        print(f"   Overwriting: {local_filename} ...")
        
        with open(local_filename, "wb") as f:
            while True:
                # 512 bytes chunk size is safe for low RAM
                chunk = s.read(512)
                if not chunk:
                    break
                f.write(chunk)
        
        s.close()
        return True

    except Exception as e:
        print(f"Error downloading {local_filename}: {e}")
        if s: s.close()
        return False
    finally:
        gc.collect()

def download_github_repo_to_update_dir():
    """
    Main Update Function.
    1. Downloads update_manifest.json
    2. Iterates and overwrites files directly.
    """
    print("\n--- Starting Direct Update ---")
    gc.collect()
    
    # Base URL for Raw Content
    base_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"
    
    headers = {'User-Agent': 'Pico-Updater'}
    if GITHUB_TOKEN:
        headers['Authorization'] = 'token {}'.format(GITHUB_TOKEN)

    # 1. Fetch Manifest
    manifest_url = f"{base_url}/update_manifest.json"
    print(f"1. Fetching manifest: {manifest_url}")
    
    manifest_list = []
    try:
        s, status = _http_request_stream(manifest_url, headers=headers)
        if status != 200:
            print(f"Manifest fetch failed (HTTP {status})")
            if s: s.close()
            return False
            
        json_str = s.read().decode('utf-8')
        s.close()
        
        manifest_list = json.loads(json_str)
        del json_str
        gc.collect()
        
    except Exception as e:
        print(f"Manifest Error: {e}")
        return False

    # 2. Process Files
    print(f"Manifest OK. Updating {len(manifest_list)} files...")
    downloaded_count = 0
    
    for item in manifest_list:
        remote_path = item['remote'] # e.g. "src/lib/writer.py"
        local_path = item['local']   # e.g. "lib/writer.py"
        
        # Build URL
        safe_remote_path = remote_path.strip("/")
        file_url = f"{base_url}/{safe_remote_path}"
        
        print(f"-> Processing: {local_path}")
        
        # Clean RAM before download
        gc.collect()
        
        # Download directly to final location
        success = download_file_blob(file_url, local_path, headers=headers)
        
        if success:
            downloaded_count += 1
        else:
            print(f"FAILED: {local_path}. System might be inconsistent.")
            return False

    print(f"\nSuccess! Updated {downloaded_count} files.")
    print("Resetting system...")
    import time
    time.sleep(1)
    machine.reset()
    return True

def trigger_update_process():
    """
    Sets the update flag and resets the device to boot into clean update mode.
    """
    print("Update requested. Rebooting into Update Mode...")
    try:
        with open("update_flag", "w") as f:
            f.write("1")
    except Exception as e:
        print(f"Error writing flag: {e}")
    
    import time
    time.sleep(0.5)
    machine.reset()