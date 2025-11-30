# async_logger.py
#
# Central, asynchronous logging system designed for MicroPython.
# It buffers log messages in memory and periodically writes them to flash storage
# with automatic file rotation to manage space constraints.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
#
import uasyncio as asyncio
from machine import RTC
import os
import sys 
import io
import gc

# --- File Configuration Constants ---
_log_file = 'system.log'
_max_log_size = 25 * 1024
_backup_log_file = 'system.log.old'

# ---------------------------
# ASYNC LOGGER CLASS
# ---------------------------
class AsyncLogger:
    """
    An asynchronous logger that buffers messages and writes them to persistent 
    storage periodically in a non-blocking manner.
    """
    def __init__(self, filename=_log_file, interval_ms=500):
        self.filename = filename
        self.interval_ms = interval_ms
        self.buffer = []
        self.rtc = RTC()
        self._lock = asyncio.Lock()
        self._current_size = 0

        try:
            self._current_size = os.stat(self.filename)[6]
        except OSError:
            self._current_size = 0

    def _get_timestamp(self):
        """Retrieves and formats the current timestamp from the RTC."""
        t = self.rtc.datetime()
        return "%02d.%02d.%04d %02d:%02d:%02d" % (t[2], t[1], t[0], t[4], t[5], t[6])

    def log(self, message, *args):
        """
        Adds message to buffer and prints to console.
        Accepts optional *args for %-style formatting.
        """
        ts = self._get_timestamp()
        
        if args:
            try:
                message = message % args
            except TypeError:
                message = str(message) + str(args)

        entry = "[%s] %s\n" % (ts, message)
        
        self.buffer.append(entry)
        print(entry.strip())

    def log_exception(self, context, exception, *args):
        """Safely logs exceptions and captures the traceback."""
        self.log("!!! EXCEPTION in %s: %s", context, exception)
        
        sys.print_exception(exception)
        
        try:
            s = io.StringIO()
            sys.print_exception(exception, s)
            s.seek(0)
            
            line = s.readline()
            while line:
                if line.strip():
                    self.buffer.append("| %s" % line)
                line = s.readline()
                
            del s
            gc.collect()

        except Exception:
            print("CRITICAL: Failed to log exception trace.")

    async def _rotate_if_needed(self):
        """Checks if the log file size exceeds the limit and performs rotation."""
        if self._current_size < _max_log_size:
            return

        try:
            self.log("--- ROTATING LOGS ---")
            await self.flush()
            
            if _backup_log_file in os.listdir():
                os.remove(_backup_log_file)
            
            os.rename(self.filename, _backup_log_file)
            self._current_size = 0
            self.log("--- LOG ROTATED ---")
        except Exception as e:
            print("Rotation failed: %s" % e)

    async def flush(self):
        """
        Manually writes the buffered messages to the disk. 
        This method is thread-safe and non-blocking, but the I/O itself is synchronous.
        """
        if not self.buffer:
            return

        async with self._lock:
            old_buffer = self.buffer
            self.buffer = []

        if not old_buffer:
            return

        try:
            with open(self.filename, "a") as f:
                for line in old_buffer:
                    f.write(line)
                    self._current_size += len(line)
            
            del old_buffer 
            gc.collect()
            
        except Exception as e:
            print("CRITICAL LOGGER WRITE ERROR: %s" % e)

    async def run(self):
        """
        The main asynchronous task. Periodically wakes up to flush the buffer
        to the flash storage in a safe, non-blocking manner.
        """
        while True:
            await asyncio.sleep_ms(self.interval_ms)
            
            await self._rotate_if_needed()
            
            await self.flush()