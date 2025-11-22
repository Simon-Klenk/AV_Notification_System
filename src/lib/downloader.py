# downloader.py
#
# Implements OTA update functionality by downloading files listed in a
# 'update_manifest.json' file from a GitHub repository.
#
# Uses streaming and raw URLs to minimize RAM usage, preventing ENOMEM errors
# on the Raspberry Pi Pico W.
#
# Author: Simon Klenk 2025
# License: MIT
#
import usocket
import ssl
import ujson as json
import os
import network
import gc
import machine

# --- Configuration ---
UPDATE_DIR = "update"
# Optional: Set token if repo is private or to avoid rate limits
GITHUB_TOKEN = "" 
REPO_OWNER = 'Simon-Klenk'
REPO_NAME = 'AV_Notification_System'
BRANCH = 'main'

def ensure_dir_exists(filepath):
    """
    Ensures that the directory structure for the given file path exists.
    Creates missing directories if necessary.
    """
    folder = "/".join(filepath.split("/")[:-1])
    if folder:
        parts = folder.split("/")
        current_path = ""
        for p in parts:
            if p:
                current_path += p + "/"
                try:
                    os.stat(current_path[:-1])
                except OSError:
                    try:
                        os.mkdir(current_path[:-1])
                        print(f"Created directory: {current_path[:-1]}")
                    except Exception as e:
                        print("Error creating directory:", current_path[:-1], e)
                        raise
        gc.collect()

def _http_request_stream(url, headers=None):
    """
    Opens a generic HTTPS connection and returns the socket stream and status code.
    This allows processing the response in chunks to save RAM.
    """
    s = None
    try:
        if url.startswith("https://"):
            url_parts = url[len("https://"):].split("/", 1)
            host = url_parts[0]
            path = "/" + url_parts[1] if len(url_parts) > 1 else "/"
        else:
            raise ValueError("Only HTTPS URLs are supported.")

        addr = usocket.getaddrinfo(host, 443)[0][-1]
        
        s = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(addr)
        
        # Aggressive garbage collection before SSL handshake (memory critical)
        gc.collect() 
        s = ssl.wrap_socket(s)

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

        # Skip remaining headers
        while True:
            line = s.readline()
            if not line or line == b"\r\n":
                break
        
        return s, status_code
    except Exception as e:
        print(f"Error in _http_request_stream: {e}")
        if s:
            s.close()
        return None, 0

def download_file_blob(url, local_filename, headers=None):
    """
    Downloads a file from a URL to the local filesystem using streaming.
    """
    ensure_dir_exists(local_filename)
    s = None
    success = False
    
    try:
        gc.collect()
        s, status_code = _http_request_stream(url, headers=headers)
        
        if status_code != 200:
            print(f"HTTP Error {status_code} while downloading {local_filename}")
            if s: s.close()
            return False

        print(f"   Writing {local_filename}...")
        with open(local_filename, "wb") as f:
            while True:
                chunk = s.read(1024)
                if not chunk:
                    break
                f.write(chunk)
        
        success = True
        print(f"   Saved: {local_filename}")

    except Exception as e:
        print(f"Error downloading {local_filename}: {e}")
        success = False
    finally:
        if s:
            try:
                s.close()
            except:
                pass
        gc.collect()
        return success

def download_github_repo_to_update_dir():
    """
    Main update function.
    1. Downloads 'update_manifest.json' from the repo root.
    2. Parses the JSON list of files.
    3. Downloads each file via raw URL to the /update folder.
    """
    print("\n--- Starting Smart Manifest Update ---\n")
    gc.collect()
    
    # Check WiFi connection
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("WiFi not connected. Aborting.")
        return False

    # Create/Verify update directory
    try:
        os.stat(UPDATE_DIR)
    except OSError:
        os.mkdir(UPDATE_DIR)

    # Base URL for raw content (always points to the latest version in the branch)
    # Format: https://raw.githubusercontent.com/{USER}/{REPO}/{BRANCH}
    base_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"
    
    headers = {'User-Agent': 'Pico-Updater'}
    if GITHUB_TOKEN:
        headers['Authorization'] = 'token {}'.format(GITHUB_TOKEN)

    # 1. Download and parse the manifest file
    manifest_url = f"{base_url}/update_manifest.json"
    print(f"1. Fetching manifest: {manifest_url}")
    
    manifest_list = []
    try:
        s, status = _http_request_stream(manifest_url, headers=headers)
        if status != 200:
            print(f"Failed to fetch manifest (HTTP {status})")
            if s: s.close()
            return False
            
        # Manifest is small enough to load into RAM (~1-2KB)
        json_str = s.read().decode('utf-8')
        s.close()
        
        manifest_list = json.loads(json_str)
        del json_str # Free memory immediately
        gc.collect()
        
    except Exception as e:
        print(f"Error processing manifest: {e}")
        return False

    # 2. Iterate through files and download them
    print(f"Manifest OK. Updating {len(manifest_list)} files...")
    downloaded_count = 0
    
    for item in manifest_list:
        remote_path = item['remote'] # e.g., "src/main.py"
        local_path = item['local']   # e.g., "main.py"
        
        # Construct the raw URL dynamically
        safe_remote_path = remote_path.strip("/")
        file_url = f"{base_url}/{safe_remote_path}"
        
        full_local_save_path = f"{UPDATE_DIR}/{local_path}"
        
        print(f"-> Downloading: {local_path}")
        
        # Clean up memory before starting a new SSL connection
        gc.collect()
        
        success = download_file_blob(file_url, full_local_save_path, headers=headers)
        
        if success:
            downloaded_count += 1
        else:
            print(f"Failed to download {local_path}. Aborting update.")
            return False

    print(f"\nUpdate complete. {downloaded_count} files updated.")
    print("Resetting system to apply changes...")
    machine.reset()
    return True