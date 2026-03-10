# main.py
#
# Main application entry point for the Raspberry Pi Pico.
# It initializes the core components, including `Hardware`, `StateManager`, and `Webserver`,
# and starts the `uasyncio` event loop to manage concurrent operations.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
#
import uasyncio as asyncio
import sys
import gc

from hardware import Hardware
from state_manager import StateManager
from async_queue import AsyncQueue
from display_manager import DisplayManager, DisplayInitializationError
import connect_wifi
import time_sync
from webserver import Webserver
from async_logger import AsyncLogger

async def show_ready_message(display_event_queue: AsyncQueue):
    message_text = "Ready"
    await display_event_queue.put({"type": "NEWTEXT", "value": message_text})
    await asyncio.sleep(3)
    await display_event_queue.put({"type": "DELETETEXT", "value": ""})

async def main(logger):
    """
    The main asynchronous function.
    Initializes shared resources, components, and starts all application tasks.
    """
    asyncio.create_task(logger.run())
    gc.collect()

    # Initialize queues for inter-task communication
    event_queue = AsyncQueue()
    display_event_queue = AsyncQueue()
    led_event_queue = AsyncQueue()
    
    try:
        # Initialize Hardware and StateManager
        hardware = Hardware(event_queue, led_event_queue)
        gc.collect()
        
        state_manager = StateManager(event_queue, display_event_queue, led_event_queue, logger)
        gc.collect()

        # Initialize DisplayManager
        task_display_manager = None
        try:
            display_manager = DisplayManager(display_event_queue, logger)
            task_display_manager = asyncio.create_task(display_manager.run())
            gc.collect()
        except DisplayInitializationError as e:
            # Catches display errors locally to keep the main application running
            logger.log("WARNING: Display initialization failed: %s", str(e))
        
    except Exception as e:
        logger.log_exception("Initialization failed", e)
        # Re-raise the error for handling by the top-level handler
        raise

    # Initialize Webserver and start the main tasks
    webserver = Webserver(event_queue, state_manager, logger)
    gc.collect()
    
    task_controll_hardware = asyncio.create_task(hardware.run())
    task_manage_state = asyncio.create_task(state_manager.run())
    task_webserver = asyncio.create_task(webserver.run())

    # Start additional background tasks
    asyncio.create_task(time_sync.sync_time(logger))

    # Show brief ready message
    asyncio.create_task(show_ready_message(display_event_queue))

    # Gather all main tasks
    tasks_to_gather = [
        task_controll_hardware, 
        task_manage_state,
        task_webserver
    ]
 
    if task_display_manager:
        tasks_to_gather.append(task_display_manager)

    logger_ref.log("Start Application Version 1.0")
        
    try:
        # Wait until all main tasks are finished (should never happen)
        await asyncio.gather(*tasks_to_gather)
        
    except Exception as e:
        logger.log_exception("CRITICAL ERROR in one of the main tasks", e)
        print("CRITICAL ERROR in one of the main tasks:")
        sys.print_exception(e)

if __name__ == "__main__":
    logger_ref = None
    try:
        # Initialize logger with reduced interval for RAM optimization (500ms)
        logger_ref = AsyncLogger(interval_ms=500)
        gc.collect()
        
        connect_wifi.connect_wifi()
        
        # Start the main application
        asyncio.run(main(logger_ref))
        
    except KeyboardInterrupt:
        logger_ref.log("Application stopped by KeyboardInterrupt.")
    except Exception as e:
        # Top-level handler for all critical startup errors
        print("\n--- CRITICAL STARTUP ERROR ---")
        sys.print_exception(e)
        
        if logger_ref:
            logger_ref.log_exception("Application CRASH (Top-Level-Handler)", e)
            # Perform emergency log flush before the program crashes/resets
            if logger_ref.buffer:
                try:
                    print("Performing emergency log flush...")
                    with open('system.log', 'a') as f:
                        for line in logger_ref.buffer:
                            f.write(line)
                except Exception as write_err:
                    print("Failed to flush logs...")
