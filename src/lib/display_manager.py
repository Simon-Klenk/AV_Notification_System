# display_manager.py
#
# This module manages the display of text on an SH1106 OLED display
# on a MicroPython device (ESP32). It uses the second core (Core 1) for
# low-level rendering and text scrolling to avoid blocking the main event loop (Core 0).
# Events are processed asynchronously via a queue.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
from machine import Pin, I2C
import uasyncio as asyncio
import sh1106
import writer 
import spleen_32 
import _thread
import utime

# ---------------------------
# configuration
# ---------------------------
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
I2C_ADDR = 0x3c
SDA_PIN = 16
SCL_PIN = 17
SCROLL_SPEED = 3
SCROLL_DELAY_MS = 1
# ---------------------------

class DisplayInitializationError(Exception):
    """Custom exception for display initialization errors."""
    pass

class DisplayManager:
    def __init__(self, display_event_queue):
        self._display_event_queue = display_event_queue 
        
        self._current_text = ""
        self.display = None
        self.writer = None 
        self.font = spleen_32 
        
        # ---------------------------
        # multi-core variables
        # ---------------------------
        self._core1_text = ""                
        self._core1_lock = _thread.allocate_lock() 
        self._core1_running = False          
        self._core1_power_on = False 

        try:
            self.i2c = I2C(0, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=400000)

            devices = self.i2c.scan()
            if not devices or I2C_ADDR not in devices:
                raise DisplayInitializationError(
                    f"I2C-Adresse {hex(I2C_ADDR)} nicht gefunden. Gefunden: {[hex(d) for d in devices]}"
                )

            self.display = sh1106.SH1106_I2C(
                DISPLAY_WIDTH, DISPLAY_HEIGHT, self.i2c, addr=I2C_ADDR, rotate=180
            )
            self.display.fill(0)
            self.display.show()
            self.display.poweroff()
            
            self.writer = writer.Writer(self.display, self.font)
            self.writer.wrap = False
            self.writer.col_clip = True 

        except Exception as e:
            raise DisplayInitializationError(f"Error initializing the display: {e}")

    # ---------------------------
    # text sanitization
    # ---------------------------
    def _sanitize_text(self, text):
        """Replaces umlauts and removes non-allowed special characters."""
        text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        text = text.replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue")
        text = text.replace("ß", "ss")
        
        sanitized_chars = []
        for char in text:
            char_code = ord(char)
            is_alphanumeric = (
                (char_code >= 48 and char_code <= 57) or  # 0-9
                (char_code >= 65 and char_code <= 90) or  # A-Z
                (char_code >= 97 and char_code <= 122)    # a-z
            )
            is_allowed_symbol = (char == " ") or (char == ".") or (char == "-")

            if is_alphanumeric or is_allowed_symbol:
                sanitized_chars.append(char)
        
        return "".join(sanitized_chars)

    # ---------------------------
    # event handling
    # ---------------------------
    def _update_text_and_power(self, new_text, power_on):
        """Safely updates text and power state for Core 1. Starts thread if necessary."""
        sanitized_text = self._sanitize_text(new_text)

        with self._core1_lock:
            self._core1_text = sanitized_text
            self._core1_power_on = power_on

        if not self._core1_running:
            _thread.start_new_thread(self._core1_scroll_thread, ())

    async def handle_event(self, event):
        """Processes NEWTEXT and DELETETEXT events."""
        event_type = event.get("type")
        
        if event_type == "NEWTEXT":
            text = event.get("value", "")
            if text != self._current_text:
                self._current_text = text
                self._update_text_and_power(text, True)
                
        elif event_type == "DELETETEXT":
            self._update_text_and_power("", False) 
            self._current_text = ""
            
        else:
            pass 

    # ---------------------------
    # calculate dimensions
    # ---------------------------
    def _calculate_dims(self, text):
        """Calculates text dimensions using the Writer."""
        
        y_start = (DISPLAY_HEIGHT - self.font.height()) // 2
        text_width = self.writer.stringlen(text)

        if text_width <= DISPLAY_WIDTH:
            x_start = (DISPLAY_WIDTH - text_width) // 2
            x_end = x_start
        else:
            x_start = DISPLAY_WIDTH
            x_end = -text_width

        return text_width, y_start, x_start, x_end

# ---------------------------
    # core 1 scroll thread
    # ---------------------------
    def _core1_scroll_thread(self):
        """Runs blocking on Core 1, handles text scrolling."""
        self._core1_running = True
        
        _text = ""
        text_width = y_start = x_start = x_end = 0
        current_x = 0.0
        last_frame_time = utime.ticks_ms()

        while self._core1_running:

            with self._core1_lock:
                new_text = self._core1_text
                is_power_on = self._core1_power_on 

            if not is_power_on:
                self.display.poweroff()
                if _text != "":
                    _text = ""
                
                utime.sleep_ms(500) 
                continue
            
            self.display.poweron() 

            if new_text != _text:
                _text = new_text
                text_width, y_start, x_start, x_end = self._calculate_dims(_text)
                current_x = float(x_start)
                
                if x_start == x_end:
                    self._render_text(_text, y_start, int(current_x))
                    continue

            if x_start != x_end:
                now = utime.ticks_ms()
                if utime.ticks_diff(now, last_frame_time) >= SCROLL_DELAY_MS:
                    self._render_text(_text, y_start, int(current_x))
                    current_x -= SCROLL_SPEED
                    
                    if current_x <= x_end:
                        current_x = x_start
                    
                    last_frame_time = now
            else:
                utime.sleep_ms(200)

    # ---------------------------
    # render text
    # ---------------------------
    def _render_text(self, text, y_start, x_start):
        """Render function that runs on Core 1 and draws text with the Writer."""
        
        devid = id(self.display)
        if devid in writer.Writer.state:
            state = writer.Writer.state[devid]
            state.text_row = y_start
            state.text_col = x_start

        self.display.fill_rect(0, y_start, DISPLAY_WIDTH, self.font.height(), 0)

        self.writer.printstring(text)

        with self._core1_lock:
            self.display.show()

    # ---------------------------
    # run function
    # ---------------------------
    async def run(self):
        """Asynchronous task that processes events and controls the display."""
        while True:
            event = await self._display_event_queue.get()
            await self.handle_event(event)