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

_message_file = 'messages.txt'
_RESOLUME_IP = '192.168.104.10'
_RESOLUME_PORT = 7000

_PARAM_PATH_OPACITY = "/composition/layers/6/video/opacity"
_PARAM_PATH = "/composition/layers/6/clips/1/video/effects/textblock/effect/text/params/lines"
_PARAM_PATH_CONNECT = "/composition/layers/6/clips/1/connect"
_PARAM_PATH_GROUP = "/composition/groups/4/video/opacity/behaviour/playdirection"


class StateManager:

    def __init__(self, event_queue, display_event_queue, led_event_queue):
        self._event_queue = event_queue
        self._display_event_queue = display_event_queue
        self._led_event_queue = led_event_queue
        self._current_state = "INITIAL"
        self._current_display_message_index = -1
        self._current_osc_index = -1
        self._messages_dirty = asyncio.Event()
        self.rtc = RTC()

        self._max_messages = 5
        self._messages = []
        self._active_resolume_task_id = 0

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._resolume_addr = (_RESOLUME_IP, _RESOLUME_PORT)

        self._ensure_message_file()
        self._load_messages_from_file()

    def _current_timestamp(self):
        t = self.rtc.datetime()
        return f"{t[2]:02d}.{t[1]:02d}.{t[0]} {t[4]:02d}:{t[5]:02d}"

    # ---------------------------
    # file management
    # ---------------------------

    def _ensure_message_file(self):
        if _message_file not in os.listdir():
            with open(_message_file, "w") as f:
                f.write("[]")

    def _load_messages_from_file(self):
        try:
            with open(_message_file, "r") as f:
                data = f.read().strip()
                self._messages = ujson.loads(data) if data else []
        except Exception:
            print("[StateManager] Error reading messages.txt.")
            self._messages = []

    def _write_messages_to_file(self):
        temp_messages = list(self._messages)
        removed_count = 0

        while len(temp_messages) > self._max_messages:
            temp_messages.pop(0)
            removed_count += 1
        
        if removed_count > 0 and self._current_display_message_index != -1:
            self._current_display_message_index = max(-1, self._current_display_message_index - removed_count)

        self._messages = temp_messages
        try:
            with open(_message_file, "w") as f:
                f.write(ujson.dumps(temp_messages))
        except Exception:
            print("[StateManager] Error writing messages.txt.")

    def get_all_messages(self):
        return list(self._messages)

    # ---------------------------
    # async file writer
    # ---------------------------

    async def _file_writer_task(self):
        while True:
            await self._messages_dirty.wait()
            self._messages_dirty.clear()
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
            raise ValueError(f"Unsupported OSC argument type: {type(arg)}")
        return msg

    def _send_resolume_message(self, path: str, value):
        try:
            if path == _PARAM_PATH_OPACITY:
                value = float(value)
            elif path == _PARAM_PATH_CONNECT:
                value = int(value)
            msg = self._osc_build_message(path, value)
            self._sock.sendto(msg, self._resolume_addr)
            print(f"[StateManager] OSC gesendet: {path} -> {value}")
        except Exception as e:
            print(f"[StateManager] Fehler beim Senden von OSC: {e}")

    # ---------------------------
    # event loop
    # ---------------------------

    async def run(self):
        asyncio.create_task(self._file_writer_task())
        while True:
            event = await self._event_queue.get()
            event_type = event.get("type", "UNKNOWN_TYPE")
            event_value = event.get("value", "UNKNOWN_VALUE")

            if event_type == "BUTTON_PRESSED":
                if event_value == "ACCEPT":
                    await self._handle_accept()
                elif event_value == "REJECT":
                    await self._handle_reject()
            elif event_type == "PICKUP":
                await self._handle_pickup(event_value)
            elif event_type == "EMERGENCY":
                await self._handle_emergency()

    # ---------------------------
    # state update
    # ---------------------------

    def update_state(self, index, new_state):
        if index != -1 and index <= len(self._messages) - 1:
            self._messages[index]["state"] = new_state
            print(self._messages[index]["state"])
            self._messages_dirty.set()
        else:
            print(f"[StateManager] Warning: Invalid index {index} for messages list")

    # ---------------------------
    # event handlers
    # ---------------------------

    async def _handle_accept(self):
        if self._current_osc_index != -1:
            self.update_state(self._current_osc_index, "show")
        if self._current_display_message_index != -1:
            self.update_state(self._current_display_message_index, "accepted")
            msg_entry = self._messages[self._current_display_message_index]

            self._active_resolume_task_id += 1
            current_task_id = self._active_resolume_task_id

            message_text = ""
            if msg_entry['type'] == "PICKUP":
                message_text = f"Die Eltern von: {msg_entry['value']} bitte zum Kids Check-in kommen"
            elif msg_entry['type'] == "EMERGENCY":
                message_text = "Ersthelfer / medizinisches Fachpersonal bitte zum Kids Check-In"

            if message_text:
                opacity_on = 1.0
                connect_on = int(opacity_on)

                self._send_resolume_message(_PARAM_PATH, message_text)
                self._send_resolume_message(_PARAM_PATH_OPACITY, opacity_on)
                self._send_resolume_message(_PARAM_PATH_CONNECT, connect_on)
                self._send_resolume_message(_PARAM_PATH_GROUP, 2)
                self._current_osc_index = self._current_display_message_index
            
            async def auto_clear(index, task_id):
                await asyncio.sleep(45)

                if task_id != self._active_resolume_task_id:
                    return

                self._send_resolume_message(_PARAM_PATH_OPACITY, 0.0)
                self._send_resolume_message(_PARAM_PATH_CONNECT, 0)
                self._send_resolume_message(_PARAM_PATH_GROUP, 0)
                self.update_state(index, "show")
                self._current_osc_index = -1

            asyncio.create_task(auto_clear(self._current_display_message_index, current_task_id))

            await self._display_event_queue.put({"type": "DELETETEXT", "value": ""})
            self._current_display_message_index = -1
            await self._led_event_queue.put({"state": "OFF"})

    async def _handle_reject(self):
        self._send_resolume_message(_PARAM_PATH, "")
        self._send_resolume_message(_PARAM_PATH_OPACITY, 0.0)
        self._send_resolume_message(_PARAM_PATH_CONNECT, 0)

        if self._current_osc_index != -1 and self._current_display_message_index == -1:
            self.update_state(self._current_osc_index, "show")
        
        if self._current_display_message_index != -1:
            self.update_state(self._current_display_message_index, "rejected")
            await self._display_event_queue.put({"type": "DELETETEXT", "value": ""})
            self._current_display_message_index = -1
            await self._led_event_queue.put({"state": "OFF"})

    async def _handle_pickup(self, pickup_value):
        entry = {
            "type": "PICKUP",
            "value": pickup_value,
            "state": "wait",
            "timestamp": self._current_timestamp()
        }
        self._messages.append(entry)
        self._current_display_message_index = len(self._messages) - 1
        self._messages_dirty.set()
        if self._current_osc_index != -1:
            self._current_osc_index = self._current_osc_index - 1

        message_text = f"Kind abholen: {pickup_value}"
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
        self._current_display_message_index = len(self._messages) - 1
        self._messages_dirty.set()
        if self._current_osc_index != -1:
            self._current_osc_index = self._current_osc_index - 1

        await self._display_event_queue.put({"type": "NEWTEXT", "value": "Ersthelfer zum Kids Check-In"})
        await self._led_event_queue.put({"state": "ON"})