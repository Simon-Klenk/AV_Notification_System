# boot.py
#
# Implements the functionality to **apply** downloaded files from a specific local subfolder
# of the MicroPython filesystem (Flash memory) to the root directory.
# It uses a **recursive move** operation to overwrite existing files/folders
# and ensures that the temporary update directory is cleaned up afterward.
# This script runs automatically at boot to finalize an update.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
#
import os
import gc

# Directory where downloaded files are temporarily placed.
UPDATE_DIR = "update"
# The root directory to which files are moved.
ROOT_DIR = "/"

def recursive_move(source_path, target_path):
    """
    Recursively moves a file or folder from source_path to target_path,
    overwriting the destination file/folder.
    """
    try:
        # Check if it is a directory (0x4000 is the directory flag in MicroPython os.stat)
        if os.stat(source_path)[0] & 0x4000:
            # It's a folder
            print(f"   -> Processing folder: {source_path}")
            
            # Create the target folder if it doesn't exist
            try:
                os.mkdir(target_path)
            except OSError as e:
                # EEXIST (Error 17) means the folder already exists, which is fine
                if e.args[0] != 17: 
                    raise e
            
            # Recursively move the contents of the source folder
            for item in os.listdir(source_path):
                recursive_move(
                    f"{source_path}/{item}", 
                    f"{target_path}/{item}"
                )
                
            # After contents are moved, delete the empty source folder
            try:
                os.rmdir(source_path)
                print(f"   -> Deleted source folder: {source_path}")
            except OSError as e:
                print(f"   ⚠️ Error deleting folder {source_path}: {e}")
        
        else:
            # It's a file - move (overwrite) directly
            try:
                os.rename(source_path, target_path) 
                print(f"   -> File moved/overwritten: **{target_path}**")
            except Exception as e:
                print(f"   ⚠️ Error moving file {source_path}: {e}")

    except OSError as e:
        print(f"   ⚠️ Error accessing {source_path}: {e}")
        
def check_and_apply_update():
    """
    Starts the recursive update process from the /update folder to the root directory.
    This function is intended to run at boot time.
    """
    print(f"🔄 boot.py: Starting RECURSIVE update check in /{UPDATE_DIR}")
    
    try:
        # 1. Check if the update folder exists
        if UPDATE_DIR not in os.listdir(ROOT_DIR):
            return

        update_items = os.listdir(UPDATE_DIR)
        
        # 2. Check if there are files/folders in the update directory
        if not update_items:
            # Only delete if empty
            try:
                os.rmdir(UPDATE_DIR)
                print(f"✅ boot.py: Empty folder '/{UPDATE_DIR}' deleted.")
            except:
                pass # Folder was likely not empty or didn't exist
            return
            
        print(f"📦 boot.py: Found items to move: {update_items}")

        # 3. Process all items in the update folder
        for item in update_items:
            source_path = f"{UPDATE_DIR}/{item}"
            target_path = f"{ROOT_DIR}{item}"
            
            recursive_move(source_path, target_path)

        # 4. Final cleanup
        # The UPDATE_DIR should now be empty and can be removed.
        try:
            os.rmdir(UPDATE_DIR)
            print(f"🎉 boot.py: Update process complete. '/{UPDATE_DIR}' deleted.")
        except OSError as e:
            print(f"⚠️ boot.py: Could not delete empty folder '/{UPDATE_DIR}': {e}")

    except Exception as e:
        print(f"🔥 boot.py: An unexpected error occurred: {e}")
    finally:
        gc.collect()
        
# Execute the function immediately upon boot
check_and_apply_update()