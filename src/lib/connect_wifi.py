# wifi_connector_sync.py
#
# This module provides synchronous functionality to connect a MicroPython device
# to a Wi-Fi network. It reads credentials from a file, decodes the password,
# and attempts to establish a connection, reporting the status and assigned IP address.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.

import time
import network
import ubinascii
from microdot import Microdot, send_file, redirect, Response

app = Microdot()
Response.default_content_type = 'application/json'


def connect_wifi():
    """
    Synchronously connects the MicroPython device to a Wi-Fi network.
    It reads the SSID and base64-encoded password from 'wifi_credentials.txt',
    decodes the password, and attempts to establish a Wi-Fi connection.
    It waits for a connection and returns the assigned IP address upon success,
    or None if the connection fails. This function will block until a connection
    is established or the timeout is reached.
    """
    ssid = None
    encoded_pw = None

    try:
        with open('wifi_credentials.txt', 'r') as f:
            lines = f.readlines()
            ssid = lines[0].strip().split(': ')[1]
            encoded_pw = lines[1].strip().split(': ')[1]
    except (OSError, IndexError, Exception):
        return None

    password = None
    try:
        password = ubinascii.a2b_base64(encoded_pw).decode('utf-8')
    except Exception:
        return None

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    while True:
        if wlan.isconnected():
            break
        time.sleep(0.5)

    if not wlan.isconnected():
        wlan.active(False)
        return None

    ip = wlan.ifconfig()[0]
    print("Wifi connecting successful: " + ip)
    return ip