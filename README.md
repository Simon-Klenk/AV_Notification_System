# AV Notification System

This project is an event-driven **MicroPython application for the Raspberry Pi Pico W**, designed to manage real-time notifications in live event environments.

It features a web interface for remote interaction and an **SH1106 OLED display** for visual alerts. By leveraging the Pico's **dual-core capabilities**, it ensures non-blocking display updates (scrolling text) while maintaining a responsive asynchronous network loop.

## 💡 Key Features

* **Dual-Core Architecture:**
    * **Core 0 (Async/`uasyncio`):** Handles the Webserver, WiFi, OSC communication, and Button logic.
    * **Core 1 (Threaded):** Dedicated to OLED rendering and smooth text scrolling, preventing slow I2C operations from blocking the main network loop.
* **Real-time State Management:** Manages message status (`wait`, `accepted`, `rejected`) and persists history to flash memory (`messages.txt`).
* **Resolume Integration (OSC/UDP):** When a notification is accepted, the message text is immediately sent via UDP/OSC to a configured Resolume Arena machine to trigger visual overlays.
* **Web Interface (`microdot`):** Provides a responsive UI for "Pickup" requests, "Emergency" alerts, and a status dashboard.
* **Smart Time Sync:** Automatic NTP synchronization including **German Daylight Saving Time (CET/CEST)** calculation.

## 📂 Module Overview

The application is structured around an asynchronous event loop. Here is what each module does:

* **`main.py`**: The entry point. Initializes all components (`Hardware`, `StateManager`, `Webserver`) and launches the `uasyncio` event loop.
* **`display_manager.py`**: Controls the SH1106 OLED. Runs a separate thread on **Core 1** to handle smooth text scrolling and sanitizes input text (e.g., replacing German umlauts).
* **`state_manager.py`**: The brain of the application. It handles incoming events, updates message status, persists data, and manages the **OSC/UDP communication** with Resolume.
* **`webserver.py`**: Sets up the Microdot HTTP server to handle requests from the web UI (`/`, `/submit`) and forwards them as events to the system.
* **`hardware.py`**: Manages physical hardware. Handles **button debouncing** via async tasks and controls the status LED.
* **`time_sync.py`**: Connects to NTP and sets the RTC with correct timezone offsets for Germany.

## 🛠️ Hardware Setup

| Component | Pin (GP) | Description |
| :--- | :--- | :--- |
| **OLED SDA** | 16 | I2C Data (SH1106) |
| **OLED SCL** | 17 | I2C Clock (SH1106) |
| **Button (Accept)** | 15 | Triggers "Show/Accept" logic |
| **Button (Reject)** | 14 | Clears current message |
| **LED (Alert)** | 2 | Visual indicator for new messages |

*Note: The I2C address for the display is expected to be `0x3c`.*

## 🚀 Installation & Setup

### 1. Dependencies
Ensure the following libraries are in your `src/lib` folder (standard in this repo):
* `uasyncio` (Built-in)
* `microdot` (Webserver)
* `sh1106` (Display Driver)
* `writer` & `spleen_32` (Font rendering)

### 2. WiFi Configuration
Use the included tool to generate your credentials file securely.
1.  Run the helper script on the Pico:
    pytools/generate_wifi_credentials.py
2.  Enter SSID and Password.
3.  The script creates `wifi_credentials.txt` automatically.

### 3. Upload
Upload the contents of the `src/` folder to the Raspberry Pi Pico W.
* **VS Code (MicroPico):** Set `"micropico.syncFolder": "src"` in settings and click Upload.
* **Pymakr:** Configure project root to `src`.

### 4. External Configuration (Resolume)
Update `state_manager.py` with your Resolume computer's IP
OSC Paths used:

Text: /composition/layers/6/clips/1/video/effects/textblock/effect/text/params/lines

Opacity: /composition/layers/6/video/opacity

🖥️ Usage Workflow
Deploy & Start: The device connects to WiFi; the IP is printed to the serial console.

Web Input: Open http://<PICO_IP> and send a "Pickup" request.

Notification: The Pico LED lights up, and the name scrolls on the OLED.

Action:

Press ACCEPT (GP15): Text is sent to Resolume (Layer Opacity -> 100%).

Press REJECT (GP14): Message is cleared locally, Resolume Layer fades out.

Auto-Clear: Accepted messages automatically fade out in Resolume after 45 seconds.

License: MIT

Author: Simon Klenk (2025)