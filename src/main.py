# main.py
#
# Main application entry point for the Raspberry Pi Pico.
# It initializes the core components, including `Hardware`, `StateManager`, and `Webserver`,
# and starts the `uasyncio` event loop to manage concurrent operations.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.

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
# from async_logger import AsyncLogger

async def show_ready_message(display_event_queue: AsyncQueue):
    message_text = "Ready"
    await display_event_queue.put({"type": "NEWTEXT", "value": message_text})
    await asyncio.sleep(3)
    await display_event_queue.put({"type": "DELETETEXT", "value": ""})

async def main():
    """
    The main asynchronous function.
    Initializes shared resources, components, and starts all application tasks.
    """

    # Initialize queues for inter-task communication
    event_queue = AsyncQueue()
    display_event_queue = AsyncQueue()
    led_event_queue = AsyncQueue()
    
    try:
        # Initialize Hardware and StateManager
        hardware = Hardware(event_queue, led_event_queue)
        gc.collect()
        
        state_manager = StateManager(event_queue, display_event_queue, led_event_queue)
        gc.collect()

        # Initialize DisplayManager
        task_display_manager = None
        try:
            display_manager = DisplayManager(display_event_queue)
            task_display_manager = asyncio.create_task(display_manager.run())
            gc.collect()
        except DisplayInitializationError as e:
            pass
        
    except Exception as e:
        raise

    # Initialize Webserver and start the main tasks
    webserver = Webserver(event_queue, state_manager)
    gc.collect()
    
    task_controll_hardware = asyncio.create_task(hardware.run())
    task_manage_state = asyncio.create_task(state_manager.run())
    task_webserver = asyncio.create_task(webserver.run())

    # Start additional background tasks
    asyncio.create_task(time_sync.sync_time())

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
        
    try:
        # Wait until all main tasks are finished (should never happen)
        await asyncio.gather(*tasks_to_gather)
        
    except Exception as e:
        print("CRITICAL ERROR in one of the main tasks:")
        sys.print_exception(e)

if __name__ == "__main__":
    try:
        connect_wifi.connect_wifi()
        # Start the main application
        asyncio.run(main())
        
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Top-level handler for all critical startup errors
        print("\n--- CRITICAL STARTUP ERROR ---")
        sys.print_exception(e)
