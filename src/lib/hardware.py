# hardware.py
#
# This module initializes hardware components (LEDs and buttons) and manages 
# debouncing and handling button interrupts (IRQs), forwarding events to the 
# main application queue.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
import machine
import uasyncio as asyncio
import utime

# ---------------------------
# configuration
# ---------------------------
_LED_ALERT_PIN = 2
_BUTTON_ACCEPT_PIN = 15
_BUTTON_REJECT_PIN = 14
# ---------------------------

# ---------------------------
# module internal variables
# ---------------------------
_latest_event = None
_event_ready = False
# ---------------------------

def _button_irq_handler(pin_id_from_lambda, pin_obj):
    """ISR to capture button presses with timestamp."""
    global _latest_event, _event_ready
    ts = utime.ticks_ms()
    _latest_event = (pin_id_from_lambda, pin_obj.value(), ts)
    _event_ready = True

# ---------------------------
# hardware class
# ---------------------------
class Hardware:
    def __init__(self, event_queue, led_event_queue):
        self._event_queue = event_queue
        self._led_event_queue = led_event_queue
        
        self._led_alert = machine.Pin(_LED_ALERT_PIN, machine.Pin.OUT)
        self._button_accept = machine.Pin(_BUTTON_ACCEPT_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)
        self._button_reject = machine.Pin(_BUTTON_REJECT_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)
        self._led_alert.value(0)

        # Attach IRQ handlers
        self._button_accept.irq(trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
                                handler=lambda p: _button_irq_handler(_BUTTON_ACCEPT_PIN, p))
        self._button_reject.irq(trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
                                 handler=lambda p: _button_irq_handler(_BUTTON_REJECT_PIN, p))

    async def _button_task(self):
        """Asynchronous task to process IRQ events with debouncing."""
        global _latest_event, _event_ready
        last_event_time = {}
        DEBOUNCE_MS = 200
        
        while True:
            if _event_ready:
                _event_ready = False
                pin_id, val, ts = _latest_event
                
                # Debounce check
                if pin_id not in last_event_time or (ts - last_event_time[pin_id]) > DEBOUNCE_MS:
                    last_event_time[pin_id] = ts
                    
                    if pin_id == _BUTTON_ACCEPT_PIN:
                        value = "ACCEPT"
                    elif pin_id == _BUTTON_REJECT_PIN:
                        value = "REJECT"
                    else:
                        value = "UNKNOWN"

                    # Put event into queue
                    await self._event_queue.put({
                        "type": "BUTTON_PRESSED" if val == 0 else "BUTTON_RELEASED",
                        "value": value,
                    })
            await asyncio.sleep_ms(100)

    async def _led_task(self):
        while True:
            event = await self._led_event_queue.get()
            event_state = event.get("state")
            
            if event_state == "ON":
                self._led_alert.value(1)

            elif event_state == "OFF":
                self._led_alert.value(0)

            else:
                pass

    # ---------------------------
    # run function
    # ---------------------------
    async def run(self):
        """Starts the button debouncing task."""
        asyncio.create_task(self._button_task())
        asyncio.create_task(self._led_task())
        while True:
            await asyncio.sleep(1)