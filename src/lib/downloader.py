# downloader.py
#
# Implements the functionality to download files from a specific branch and subfolder
# of a GitHub repository directly to the MicroPython filesystem (Flash memory).
# It uses streaming to minimize RAM usage for large files and requires a
# Personal Access Token (PAT) for reliable operation.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
#
import usocket
import ssl
import time
import ujson as json
import os
import network
import ubinascii
import gc
import machine

# --- Configuration ---
UPDATE_DIR = "update"
GITHUB_TOKEN = ""
REPO_OWNER = 'Simon-Klenk'
REPO_NAME = 'AV_Notification_System'
BRANCH = 'main'

# Only files from this subfolder of the repository will be downloaded
REPO_SUBFOLDER = "src/"

def ensure_dir_exists(filepath):
    """Ensures that the directory structure for the given file path exists."""
    # The folder we need to create is everything before the last slash
    folder = "/".join(filepath.split("/")[:-1])
    if folder:
        parts = folder.split("/")
        current_path = ""
        for p in parts:
            if p:
                current_path += p + "/"
                # Try to stat the folder (check if it exists)
                try:
                    os.stat(current_path[:-1])
                except OSError:
                    # Folder does not exist, try to create it
                    try:
                        os.mkdir(current_path[:-1])
                        print(f"Folder '{current_path[:-1]}' created.")
                    except Exception as e:
                        print("✖ Could not create folder:", current_path[:-1], e)
                        raise
        gc.collect()

def _http_request_stream(url, headers=None):
    """Generic HTTPS request client, returns the socket stream and status code."""
    s = None
    try:
        if url.startswith("https://"):
            url_parts = url[len("https://"):].split("/", 1)
            host = url_parts[0]
            # The path always includes a leading slash
            path = "/" + url_parts[1] if len(url_parts) > 1 else "/"
        else:
            raise ValueError("Only HTTPS URLs are supported.")

        # DNS Resolution
        addr = usocket.getaddrinfo(host, 443)[0][-1]
        
        # Create and connect socket
        s = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(addr)
        
        # SSL/TLS wrapper for secure connection
        s = ssl.wrap_socket(s)

        # Create HTTP request
        request_lines = [
            "GET {} HTTP/1.0".format(path),
            "Host: {}".format(host),
        ]
        if headers:
            for key, value in headers.items():
                request_lines.append("{}: {}".format(key, value))
        # End headers with an empty line
        request_lines.append("\r\n")
        s.write("\r\n".join(request_lines).encode('utf-8'))

        # Read header and extract status code
        status_line = s.readline().decode('utf-8').strip()
        parts = status_line.split(' ')
        status_code = int(parts[1]) if len(parts) > 1 else 0

        # Discard all remaining headers (until the empty line before the body)
        while True:
            line = s.readline()
            if not line or line == b"\r\n":
                break
        
        # Return the status-aware socket stream and the status code
        return s, status_code
    except Exception as e:
        print(f"✖ Error in _http_request_stream for {url}: {e}")
        if 's' in locals() and s:
            s.close()
        # On error, status code is unknown (0) and stream is None
        return None, 0

def download_file_blob(url, local_filename, headers=None):
    """
    Downloads a file via stream. Uses the GitHub Raw header to completely
    bypass JSON/Base64 parsing in RAM.
    """
    ensure_dir_exists(local_filename)
    s = None
    success = False
    
    # Copy headers to avoid modifying the original dict
    request_headers = headers.copy() if headers else {}
    request_headers['Accept'] = 'application/vnd.github.v3.raw'
    
    try:
        gc.collect() # Cleanup before starting
        
        # Start request
        s, status_code = _http_request_stream(url, headers=request_headers)
        
        if status_code != 200:
            print(f"✖ HTTP Error {status_code} for {local_filename}")
            # Cleanly exits here on 404 or 403
            if s: s.close()
            return False

        print(f"    ...writing {local_filename} (Stream)...")

        # Stream file directly from socket to Flash memory
        # RAM usage: Constant approx. 1KB (buffer), regardless of file size.
        with open(local_filename, "wb") as f:
            while True:
                chunk = s.read(1024) # 1KB Chunks
                if not chunk:
                    break
                f.write(chunk)
        
        s.close()
        success = True
        print(f"✔ File saved: {local_filename}")

    except Exception as e:
        print(f"✖ Error during download of {local_filename}: {e}")
        success = False
    finally:
        if s:
            try:
                s.close()
            except:
                pass
        gc.collect() # Immediately free memory for the next round
        return success

def parse_github_tree_response(json_data_string):
    """Parses the GitHub Tree API response and filters for the src/ folder."""
    try:
        data = json.loads(json_data_string)
    except ValueError as e:
        print(f"✖ Error parsing JSON data: {e}")
        return []

    parsed_files = []
    if "tree" in data:
        for item in data["tree"]:
            # Filter logic: Only files ("blob") in the defined subfolder, and not hidden files
            if (item["type"] == "blob" and
                not item["path"].startswith('.') and
                item["path"].startswith(REPO_SUBFOLDER)):
                
                # Remove the "src/" prefix for local storage (e.g., src/main.py -> main.py)
                local_path_after_filter = item["path"][len(REPO_SUBFOLDER):]
                
                # Directory path of the blob must not be empty (e.g., no root files like 'src/').
                if local_path_after_filter: 
                    parsed_files.append({
                        "repo_path": item["path"], 
                        "blob_url": item["url"],
                        "local_save_path": local_path_after_filter 
                    })
    return parsed_files

# --- Main Function ---

def download_github_repo_to_update_dir():
    """
    Downloads only files from the configured subfolder into the /update directory.
    Returns True if the download was successful, otherwise False.
    """
    gc.collect()
    
    # Create authenticated headers
    headers = {
        'User-Agent': 'MicroPython-Pico-GitHub-Client',
    }
    # Only add if a token is available
    if GITHUB_TOKEN:
        headers['Authorization'] = 'token {}'.format(GITHUB_TOKEN)
        print("Authentication: GitHub Token is being used.")
    else:
        print("⚠️ Warning: No GitHub Token set. Rate limit of 60 requests/hour will apply.")
    
    github_tree_api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/{BRANCH}?recursive=1"
    
    print(f"🔄 Starting download from {REPO_OWNER}/{REPO_NAME}@{BRANCH} (Filter: {REPO_SUBFOLDER})")
    
    # WiFi check
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("⚠️ WiFi is not connected. Download aborted.")
        return False
        
    try:
        # Create the update folder if it doesn't exist
        try:
            os.stat(UPDATE_DIR)
        except OSError:
            os.mkdir(UPDATE_DIR)
            print(f"Folder **'/{UPDATE_DIR}'** created.")
            
        s_api = None
    
        # 1. Retrieve GitHub Repository Structure (using authenticated headers)
        s_api, status_code = _http_request_stream(github_tree_api_url, headers=headers)
        
        if s_api is None or status_code != 200:
            # Error report, especially for 403 (Rate limit)
            if status_code == 403:
                print("✖ 403 FORBIDDEN: Rate limit reached or invalid/missing GitHub Token.")
                if not GITHUB_TOKEN:
                    print("Solution: Please set a Personal Access Token.")
            print(f"✖ Error retrieving repository structure: HTTP {status_code}")
            return False

        # Read the entire JSON response from the stream
        github_json_response_bytes = b""
        while True:
            chunk = s_api.read(1024)
            if not chunk:
                break
            github_json_response_bytes += chunk
        s_api.close()
        s_api = None
        
        gc.collect() 
        print(f"Memory available before Parse: {gc.mem_free()} Bytes")

        # Parse and filter JSON
        github_files_remote = parse_github_tree_response(github_json_response_bytes.decode('utf-8'))
        
        del github_json_response_bytes 
        gc.collect()
        print(f"Memory available after Parse: {gc.mem_free()} Bytes")

        if not github_files_remote:
            print("✖ No files received after filtering.")
            return False

        # 2. Download files and save them in the /update folder
        downloaded_count = 0
        for item in github_files_remote:
            repo_path_root = item['repo_path'] 
            local_save_path_filtered = item['local_save_path']
            # The path under which the file is saved in the 'update' folder
            local_update_path = f"{UPDATE_DIR}/{local_save_path_filtered}" 
            
            print(f"-> Downloading: '{repo_path_root}' -> '/{local_update_path}'")
            # Download each file using the AUTHENTICATED headers
            success = download_file_blob(item['blob_url'], local_update_path, headers=headers)
            if success:
                downloaded_count += 1
            
        print(f"\n🎉 Download complete. **{downloaded_count} files** saved in '/{UPDATE_DIR}'.")
        # Trigger system reset to apply the update immediately
        machine.reset() 
        return True
        
    except Exception as e:
        print(f"🔥 A general error occurred: {e}")
        return False
    finally:
        if s_api:
            s_api.close()
        gc.collect()