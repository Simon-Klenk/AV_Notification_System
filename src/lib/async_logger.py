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

# --- File Configuration Constants ---
_log_file = 'system.log'
_max_log_size = 20 * 1024  # 20 KB Limit for Logs on resource-constrained devices
_backup_log_file = 'system.log.old'

# ---------------------------
# ASYNC LOGGER CLASS
# ---------------------------
class AsyncLogger:
    """
    An asynchronous logger that buffers messages and writes them to persistent 
    storage periodically in a non-blocking manner.
    """
    def __init__(self, filename=_log_file, interval_ms=5000):
        self.filename = filename
        self.interval_ms = interval_ms
        self.buffer = [] # In-memory list to store pending log entries
        self.rtc = RTC() # Real-Time Clock for accurate timestamps
        self._lock = asyncio.Lock() # Lock to protect the buffer during concurrent access
        
    def _get_timestamp(self):
        """Retrieves and formats the current timestamp from the RTC."""
        t = self.rtc.datetime()
        # Format: DD.MM.YYYY HH:MM:SS
        return "{:02d}.{:02d}.{:04d} {:02d}:{:02d}:{:02d}".format(t[2], t[1], t[0], t[4], t[5], t[6])

    def log(self, message):
        """
        Adds a message to the internal buffer. This operation is non-blocking.
        The message is also immediately printed to the console/REPL for real-time debugging.
        """
        ts = self._get_timestamp()
        entry = f"[{ts}] {message}"
        self.buffer.append(entry)
        print(entry) 

    def log_exception(self, context, exception):
        """
        Logs a detailed exception including context and traceback, ensuring
        critical errors are captured persistently.
        """
        try:
            # Capture the traceback string
            import io
            s = io.StringIO()
            sys.print_exception(exception, s)
            traceback_str = s.getvalue().strip()
            
            self.log(f"EXCEPTION in {context}: {exception}")
            for line in traceback_str.split('\n'):
                self.log(f"TRACE: {line.strip()}")
        except Exception as e:
            # Fallback in case logging the original exception fails
            self.log(f"WARNING: Failed to log exception in {context}: {e}")

    async def _check_rotation(self):
        """
        Checks the primary log file size and performs a single-backup rotation 
        if the size limit is exceeded.
        """
        try:
            stat = os.stat(self.filename)
            if stat[6] > _max_log_size:
                # Atomically rotate: delete old backup, rename current to backup.
                try:
                    if _backup_log_file in os.listdir():
                        os.remove(_backup_log_file)
                    os.rename(self.filename, _backup_log_file)
                    self.log(f"Log rotated (Limit {_max_log_size}B reached). Current log is now {_backup_log_file}.")
                except Exception as e:
                    self.log(f"Error during rotation: {e}")
        except OSError:
            # File does not exist yet; safe to ignore
            pass

    async def run(self):
        """
        The main asynchronous task. Periodically wakes up to flush the buffer
        to the flash storage in a safe, non-blocking manner.
        """
        while True:
            # Wait for the specified interval
            await asyncio.sleep_ms(self.interval_ms)
            
            if self.buffer:
                # Use lock to safely swap the buffer and prevent race conditions 
                # if log() is called concurrently.
                async with self._lock:
                    current_chunk = self.buffer[:]
                    self.buffer = []
                
                try:
                    # Check and perform rotation before writing
                    await self._check_rotation()
                    
                    # Blocking I/O operation (writing to flash), but minimized 
                    # in frequency by the interval and buffer chunking.
                    with open(self.filename, "a") as f:
                        for line in current_chunk:
                            f.write(line + "\n")
                except Exception as e:
                    # Critical error: Failed to write to flash. Log to console only.
                    print(f"CRITICAL LOGGER WRITE ERROR: {e}")