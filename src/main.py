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
from hardware import Hardware
from state_manager import StateManager
from async_queue import AsyncQueue
from display_manager import DisplayManager
import connect_wifi
import time_sync
from webserver import Webserver

async def show_ready_message(display_event_queue: AsyncQueue):
    """
    Writes the text "Bereit" to the display queue, waits 4 seconds, and then deletes it.
    """
    message_text = "Bereit"
    
    await display_event_queue.put({"type": "NEWTEXT", "value": message_text})
    await asyncio.sleep(3)
    await display_event_queue.put({"type": "DELETETEXT", "value": ""})
    

async def main():
    """
    The main asynchronous function.
    Initializes shared resources, components, and starts all application tasks.
    """
    
    # 1. Initialize Shared Asynchronous Queues
    # Queues are used for inter-component communication (e.g., button press to state change).
    event_queue = AsyncQueue()
    display_event_queue = AsyncQueue()
    led_event_queue = AsyncQueue()
    
    # 2. Initialize Core Components
    # Inject queues for decoupled communication.
    hardware = Hardware(event_queue, led_event_queue)
    state_manager = StateManager(event_queue, display_event_queue, led_event_queue)
    webserver = Webserver(event_queue, state_manager)
    # The DisplayManager typically runs on the second core (Core 1) for performance.
    display_manager = DisplayManager(display_event_queue)

    # 3. Create and Start Background Tasks (Coroutines)
    # These tasks run concurrently within the uasyncio event loop.
    task_syc_time = asyncio.create_task(time_sync.sync_time())
    task_controll_hardware = asyncio.create_task(hardware.run())
    task_manage_state = asyncio.create_task(state_manager.run())
    task_webserver = asyncio.create_task(webserver.run())

    # Display manager run task (a placeholder for the Core 1 execution).
    task_display_manager = asyncio.create_task(display_manager.run())
    
    # --- Start the task to show and delete the "bereit" message ---
    task_ready_message = asyncio.create_task(show_ready_message(display_event_queue))
    
    # 4. Wait for All Persistent Tasks
    try:
        await asyncio.gather(
            task_controll_hardware, 
            task_manage_state,
            task_webserver,
            task_display_manager
        )
    except Exception as e:
        sys.print_exception(e)
    finally:
        pass

if __name__ == "__main__":
    try:
        connect_wifi.connect_wifi()
        asyncio.run(main())
        
    except KeyboardInterrupt:
        pass
    except Exception as e:
        sys.print_exception(e)
    finally:
        pass