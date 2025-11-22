# boot.py
#
# Runs immediately on startup.
# Checks for an 'update_flag' file. If found, it boots into a minimal
# update mode to maximize RAM for the SSL download process.
# Otherwise, it passes control to main.py.
#
import machine
import os
import gc
import connect_wifi
import time 

def do_update():
    connect_wifi.connect_wifi()
    
    try:
        import lib.downloader as downloader
        success = downloader.download_github_repo_to_update_dir()
            
        if success:
            print("Update succesfull...")
            os.remove("update_flag")
        else:
            print("Update error")
            os.remove("update_flag")
                
    except Exception as e:
        print(f"Critical Error: {e}")
        try:
            os.remove("update_flag")
        except:
            pass
    else:
        print("No wlan connection.")
        try:
            os.remove("update_flag")
        except:
            pass

    print("Resetting...")
    time.sleep(1)
    machine.reset()

try:
    os.stat("update_flag")
    FLAG_EXISTS = True
except OSError:
    FLAG_EXISTS = False

if FLAG_EXISTS:
    gc.collect()
    do_update()
else:
    print("Boot without update...")