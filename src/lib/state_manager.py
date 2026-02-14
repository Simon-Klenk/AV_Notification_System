# state_manager.py
#
# This module manages the application state, message history, and persistence
# on a MicroPython device. It processes incoming events, updates the message
# state, and handles communication with the display manager.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.

import uasyncio as asyncio
from machine import RTC
import ujson
import os
import usocket as socket
import struct
import gc

_message_file = 'messages.txt'
_RESOLUME_IP = '192.168.104.10'
_RESOLUME_PORT = 7000

# ---------------------------
# STATE MANAGER
# ---------------------------

class StateManager:

    _PARAM_PATH_OPACITY = "/composition/layers/6/video/opacity"
    _PARAM_PATH = "/composition/layers/6/clips/1/video/effects/textblock/effect/text/params/lines"
    _PARAM_PATH_CONNECT = "/composition/layers/6/clips/1/connect"

    def __init__(self, event_queue, display_event_queue, led_event_queue, logger):
        self._event_queue = event_queue
        self._display_event_queue = display_event_queue
        self._led_event_queue = led_event_queue
        self._current_state = "INITIAL"
        self._current_display_message_index = -1
        self._current_osc_index = -1
        self._messages_dirty = asyncio.Event()
        self.rtc = RTC()
        self.logger = logger

        self._max_messages = 5
        self._messages = []
        self._active_resolume_task_id = 0

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._resolume_addr = (_RESOLUME_IP, _RESOLUME_PORT)

        self._ensure_message_file()
        self._load_messages_from_file()

        self.logger.log("StateManager initialized.")

    def _current_timestamp(self):
        t = self.rtc.datetime()
        return "%02d.%02d.%d %02d:%02d" % (t[2], t[1], t[0], t[4], t[5])

    # ---------------------------
    # file management
    # ---------------------------

    def _ensure_message_file(self):
        if _message_file not in os.listdir():
            self.logger.log("Creating missing message file: %s", _message_file)
            try:
                with open(_message_file, "w") as f:
                    f.write("[]")
            except Exception as e:
                self.logger.log_exception("_ensure_message_file", e)

    def _load_messages_from_file(self):
        try:
            with open(_message_file, "r") as f:
                data = f.read().strip()
                self._messages = ujson.loads(data) if data else []
            self.logger.log("Loaded %d messages from file.", len(self._messages))
        except Exception as e:
            self.logger.log_exception("_load_messages_from_file", e)
            self._messages = []
        gc.collect()

    def _write_messages_to_file(self):
        removed_count = 0
        list_len = len(self._messages)
        
        if list_len > self._max_messages:
            removed_count = list_len - self._max_messages
            self._messages = self._messages[removed_count:]

            if self._current_display_message_index != -1:
                self._current_display_message_index = max(-1, self._current_display_message_index - removed_count)
        
        if removed_count > 0:
            self.logger.log("Removed %d old messages to maintain limit.", removed_count)
            
        try:
            with open(_message_file, "w") as f:
                f.write(ujson.dumps(self._messages))
            self.logger.log("Wrote %d messages to file.", len(self._messages))
        except Exception as e:
            self.logger.log_exception("_write_messages_to_file", e)
        
        gc.collect()

    def get_all_messages(self):
        return list(self._messages)

    # ---------------------------
    # async file writer
    # ---------------------------

    async def _file_writer_task(self):
        while True:
            await self._messages_dirty.wait()
            self._messages_dirty.clear()
            self.logger.log("Message file flagged dirty. Waiting 500ms before write...")
            await asyncio.sleep_ms(500)
            self._write_messages_to_file()

    # ---------------------------
    # OSC helpers
    # ---------------------------

    def _osc_encode_string(self, s: str) -> bytes:
        b = s.encode('utf-8') + b'\x00'
        padding = (4 - len(b) % 4) % 4
        return b + (b'\x00' * padding)

    def _osc_encode_float(self, f: float) -> bytes:
        return struct.pack('>f', f)

    def _osc_encode_int(self, i: int) -> bytes:
        return struct.pack('>i', i)

    def _osc_build_message(self, address: str, arg) -> bytes:
        msg = self._osc_encode_string(address)
        if isinstance(arg, int):
            msg += self._osc_encode_string(",i") + self._osc_encode_int(arg)
        elif isinstance(arg, float):
            msg += self._osc_encode_string(",f") + self._osc_encode_float(arg)
        elif isinstance(arg, str):
            msg += self._osc_encode_string(",s") + self._osc_encode_string(arg)
        else:
            self.logger.log("Error: Unsupported OSC argument type: %s", type(arg))
            raise ValueError("Unsupported OSC argument type: %s" % type(arg))
        return msg

    def _send_resolume_message(self, path: str, value):
        try:
            if path == self._PARAM_PATH_OPACITY:
                value = float(value)
            elif path == self._PARAM_PATH_CONNECT:
                value = int(value)
                
            msg = self._osc_build_message(path, value)
            self._sock.sendto(msg, self._resolume_addr)
            self.logger.log("OSC sent: %s -> %s", path, value)
        except ValueError as ve:
            self.logger.log("OSC encoding error: %s", ve)
        except Exception as e:
            self.logger.log_exception("_send_resolume_message", e)

    # ---------------------------
    # event loop
    # ---------------------------

    async def run(self):
        asyncio.create_task(self._file_writer_task())
        self.logger.log("Event Loop started.")
        
        while True:
            self.logger.log("Waiting for next event from queue...")
            event = await self._event_queue.get()
            event_type = event.get("type", "UNKNOWN_TYPE")
            event_value = event.get("value", "UNKNOWN_VALUE")
            
            self.logger.log("Event received: %s - %s", event_type, event_value)

            try:
                if event_type == "BUTTON_PRESSED":
                    if event_value == "ACCEPT":
                        await self._handle_accept()
                    elif event_value == "REJECT":
                        await self._handle_reject()
                    else:
                        self.logger.log("Unknown BUTTON_PRESSED value: %s", event_value)
                elif event_type == "PICKUP":
                    await self._handle_pickup(event_value)
                elif event_type == "PARKING":
                    await self._handle_parking(event_value)
                elif event_type == "EMERGENCY":
                    await self._handle_emergency()
                else:
                    self.logger.log("Unknown event type received: %s", event_type)
            except Exception as e:
                self.logger.log_exception("Handler for %s", e)
                
    # ---------------------------
    # Auto-Clear Task
    # ---------------------------
    async def _auto_clear_task(self, index, task_id):
        await asyncio.sleep(45)

        if task_id != self._active_resolume_task_id:
            self.logger.log("Auto-Clear aborted: Newer task (%d) active.", self._active_resolume_task_id)
            return

        self.logger.log("Auto-Clear executed: Setting opacity to 0.0")
        
        self._send_resolume_message(self._PARAM_PATH_OPACITY, 0.0)
        self._send_resolume_message(self._PARAM_PATH_CONNECT, 0)
        
        if index != -1 and self._current_osc_index == index:
            self.update_state(index, "show")
            self._current_osc_index = -1
        else:
            self.logger.log("Auto-Clear: Index mismatch or already cleared.")
            
        self.logger.log("OSC Auto-Clear completed.")


    # ---------------------------
    # state update
    # ---------------------------

    def update_state(self, index, new_state):
        if index != -1 and index <= len(self._messages) - 1:
            self._messages[index]["state"] = new_state
            self.logger.log("State update idx %d: %s", index, new_state)
            self._messages_dirty.set()
        else:
            self.logger.log("Warning: Invalid index %d for messages list update.", index)

    # ---------------------------
    # event handlers
    # ---------------------------

    async def _handle_accept(self):
        self.logger.log("Pressed accept")
        if self._current_osc_index != -1:
            self.update_state(self._current_osc_index, "show")
        
        if self._current_display_message_index != -1:
            msg_entry = self._messages[self._current_display_message_index]
            
            self.logger.log("Message accepted: Type=%s, Value='%s' (Index: %d)", msg_entry['type'], msg_entry['value'], self._current_display_message_index)
            
            self.update_state(self._current_display_message_index, "accepted")

            message_text = ""
            if msg_entry['type'] == "PICKUP":
                message_text = "Die Eltern von %s bitte zum Kids Check-in kommen" % msg_entry['value']
            elif msg_entry['type'] == "PARKING":
                message_text = "Fahrzeug bitte umparken:\n%s" % msg_entry['value']
            elif msg_entry['type'] == "EMERGENCY":
                message_text = "Ersthelfer / medizinisches Fachpersonal bitte zum Kids Check-In"

            if message_text:
                opacity_on = 1.0
                connect_on = int(opacity_on)                

                self._send_resolume_message(self._PARAM_PATH, message_text)
                await asyncio.sleep_ms(50)
                self._send_resolume_message(self._PARAM_PATH_OPACITY, opacity_on)
                await asyncio.sleep_ms(50)
                self._send_resolume_message(self._PARAM_PATH_CONNECT, connect_on)
                self._current_osc_index = self._current_display_message_index
            
            self._active_resolume_task_id += 1
            current_task_id = self._active_resolume_task_id

            asyncio.create_task(self._auto_clear_task(self._current_display_message_index, current_task_id))

            await self._display_event_queue.put({"type": "DELETETEXT", "value": ""})
            self._current_display_message_index = -1
            await self._led_event_queue.put({"state": "OFF"})
        else:
            self.logger.log("REJECT skipped: No message currently selected for ACCEPT.")

    async def _handle_reject(self):
        self.logger.log("Handling REJECT: Message rejected, Resolume display cleared.")
        
        self.logger.log("OSC Sending: Text cleared (Path: %s)", self._PARAM_PATH)
        self.logger.log("OSC Sending: Opacity OFF (0.0) (Path: %s)", self._PARAM_PATH_OPACITY)
        self._send_resolume_message(self._PARAM_PATH, "")
        self._send_resolume_message(self._PARAM_PATH_OPACITY, 0.0)
        self._send_resolume_message(self._PARAM_PATH_CONNECT, 0)
        
        if self._current_osc_index != -1 and self._current_display_message_index == -1:
            self.update_state(self._current_osc_index, "show")
            self._current_osc_index = -1
        
        if self._current_display_message_index != -1:
            msg_entry = self._messages[self._current_display_message_index]
            
            self.logger.log("Message rejected: Type=%s, Value='%s' (Index: %d)", msg_entry['type'], msg_entry['value'], self._current_display_message_index)
            
            self.update_state(self._current_display_message_index, "rejected")
            await self._display_event_queue.put({"type": "DELETETEXT", "value": ""})
            self._current_display_message_index = -1
            await self._led_event_queue.put({"state": "OFF"})
        else:
            self.logger.log("REJECT skipped: No message currently selected for REJECT.")

    async def _handle_pickup(self, pickup_value):
        entry = {
            "type": "PICKUP",
            "value": pickup_value,
            "state": "wait",
            "timestamp": self._current_timestamp()
        }
        self._messages.append(entry)
        if len(self._messages) > 6:
            self._messages.pop(0)
        self._current_display_message_index = len(self._messages) - 1
        self._messages_dirty.set()

        self.logger.log("New message added: Type=PICKUP, Value='%s', Index=%d", pickup_value, self._current_display_message_index)

        message_text = "Kind abholen: %s" % pickup_value
        await self._display_event_queue.put({"type": "NEWTEXT", "value": message_text})
        await self._led_event_queue.put({"state": "ON"})

    async def _handle_emergency(self):
        entry = {
            "type": "EMERGENCY",
            "value": "Ersthelfer / medizinisches Fachpersonal bitte zum Kids Check-In",
            "state": "wait",
            "timestamp": self._current_timestamp()
        }
        self._messages.append(entry)
        if len(self._messages) > 6:
            self._messages.pop(0)
        self._current_display_message_index = len(self._messages) - 1
        self._messages_dirty.set()

        self.logger.log("New message added: Type=EMERGENCY, Index=%d", self._current_display_message_index)

        await self._display_event_queue.put({"type": "NEWTEXT", "value": "Ersthelfer zum Check-In"})
        await self._led_event_queue.put({"state": "ON"})
    
    async def _handle_parking(self, plate_value):
        entry = {
            "type": "PARKING",
            "value": plate_value,
            "state": "wait",
            "timestamp": self._current_timestamp()
        }
        self._messages.append(entry)
        if len(self._messages) > 6:
            self._messages.pop(0)
        self._current_display_message_index = len(self._messages) - 1
        self._current_display_message_index = len(self._messages) - 1
        self._messages_dirty.set()

        self.logger.log("New message added: Type=PARKING, Value='%s', Index=%d", plate_value, self._current_display_message_index)

        message_text = "Umparken: %s" % plate_value
        await self._display_event_queue.put({"type": "NEWTEXT", "value": message_text})
        await self._led_event_queue.put({"state": "ON"})