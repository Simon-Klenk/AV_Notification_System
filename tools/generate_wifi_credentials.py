# wifi_credential_manager.py
#
# This script provides a utility to securely save Wi-Fi credentials
# (SSID and password) to a file on a MicroPython device.
# The password is base64 encoded before saving.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.

import ubinascii

def save_wifi_credentials():
    """
    Prompts the user to enter the Wi-Fi name (SSID) and password.
    The password is then base64 encoded for basic obfuscation before being
    saved along with the SSID to a file named 'wifi_credentials.txt'.
    """

    ssid = input("Please enter the Wi-Fi name (SSID): ")
    password = input("Please enter the Wi-Fi password: ")

    encoded_password = ubinascii.b2a_base64(password.encode('utf-8')).decode('utf-8').strip()

    # Save Wi-Fi name and the base64-encoded password to a file.
    with open('wifi_credentials.txt', 'w') as f:
        f.write(f"SSID: {ssid}\n") # Write the SSID followed by a newline
        f.write(f"Password: {encoded_password}") # Write the encoded password

    print("Wi-Fi credentials have been saved to 'wifi_credentials.txt'.")

save_wifi_credentials()