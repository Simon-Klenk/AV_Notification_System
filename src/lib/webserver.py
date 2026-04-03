# webserver.py 
# 
# This module implements the Microdot web server for user interaction, 
# handling incoming requests from the web UI and forwarding them to 
# the main application event queue. 
# 
# Author: Simon Klenk 2025 
# License: MIT - See the LICENSE file in the project directory for the full license text.

import network
from microdot import Microdot, send_file, redirect, Response
from async_logger import _log_file, _backup_log_file

app = Microdot()
Response.default_content_type = 'application/json'

# --------------------------- 
# webserver class 
# --------------------------- 
class Webserver: 
    """
    Implements the Microdot web server to serve static HTML pages 
    and handle API endpoints for application control.
    """
    def __init__(self, event_queue, state_manager, base_dir="/html"): 
        self._base_dir = base_dir 
        self._event_queue = event_queue 
        self.page_files = self._create_page_files() 
        self.state_manager = state_manager

    def _create_page_files(self): 
        """Defines the paths for the static HTML pages.""" 
        return { 
            'pickup': f'{self._base_dir}/pickup.html', 
            'status': f'{self._base_dir}/status.html', 
            'emergency': f'{self._base_dir}/emergency.html', 
            'system': f'{self._base_dir}/system.html',
            'parking': f'{self._base_dir}/parking.html'
        } 

    # --------------------------- 
    # routes 
    # --------------------------- 
    async def index(self, request): 
        """
        Serves the correct HTML file based on the 'page' query parameter. 
        The default page is 'pickup'.
        """ 
        page = request.args.get('page', 'pickup') 
        file = self.page_files.get(page, self.page_files['pickup']) 
    

        try: 
            return send_file(file, max_age=0) 
        except Exception as e:
            return "404 - File not found", 404 

    async def handle_post(self, request): 
        """Handles form submissions and puts corresponding events into the queue.""" 
        form = request.form
        msg_content = form.get('content')
        msg_emergency = form.get('emergency_type')
        msg_plate = form.get('plate_number')

        if msg_content:
            await self._event_queue.put({
                "type": "PICKUP",
                "value": msg_content,
            })

        elif msg_plate:
            await self._event_queue.put({
                "type": "PARKING",
                "value": msg_plate,
            })

        elif msg_emergency: 
            # Assuming 'staff' is the key for triggering the EMERGENCY event
            if msg_emergency.lower() == "staff":
                await self._event_queue.put({
                    "type": "EMERGENCY",
                })

        # Redirect back to the status page after submission
        return redirect('/?page=status') 

    async def show_messages(self, request): 
        """API endpoint to retrieve the last 5 messages for the status page.""" 
        # Assumes state_manager.get_all_messages() returns a list of messages
        msgs = self.state_manager.get_all_messages() 
        return {'messages': msgs[-5:]}

    async def show_log(self, request):
            """
            API endpoint to retrieve the system log file content by streaming 
            data to avoid MemoryError on constrained devices.
            
            Uses a generator function (log_streamer) to yield content line-by-line.
            """
            
            async def log_streamer():
                """Generator that yields log content in small chunks."""
                
                # 1. Stream current log (system.log)
                # Send the header first
                yield "\n--- system.log ---\n".encode('utf-8')
                
                try:
                    # Open the file and stream line by line
                    with open(_log_file, 'r') as f:
                        while True:
                            # Use readline to read only one line at a time into RAM
                            line = f.readline() 
                            if not line:
                                break
                            # Yield the line (must be bytes for HTTP response body)
                            yield line.encode('utf-8')
                except OSError as e:
                    yield "\n--- system.log: Not found ---\n".encode('utf-8')
                except Exception as e:
                    yield "\n--- system.log: CRITICAL READ ERROR ---\n".encode('utf-8')

                # 2. Stream backup log (system.log.old)
                # Send the header for the backup log
                yield "\n\n--- system.log.old ---\n".encode('utf-8')
                
                try:
                    # Open and stream the backup file
                    with open(_backup_log_file, 'r') as f:
                        while True:
                            line = f.readline()
                            if not line:
                                break
                            yield line.encode('utf-8')
                except OSError as e:
                    yield "\n--- system.log.old: Not found ---\n".encode('utf-8')
                except Exception as e:
                    yield "\n--- system.log.old: CRITICAL READ ERROR ---\n".encode('utf-8')


            # Return a Response object, passing the generator as the body.
            # Microdot/MicroPython will execute the generator and send chunks 
            # to the client sequentially, keeping RAM usage low.
            return Response(
                body=log_streamer(), 
                status_code=200, 
                headers={'Content-Type': 'text/plain'}
            )
    
    async def handle_update_trigger(self, request): 
        """
        API endpoint to trigger a system update via the downloader module.
        This function is only called via POST (button click) as configured in run().
        """ 
        
        # Write the update flag before the reset
        
        with open("update_flag", "w") as f:
            f.write("1")
            
        import machine
        import time
        time.sleep(0.5)
        machine.reset()

    # --------------------------- 
    # main loop 
    # --------------------------- 
    async def run(self): 
        """Starts the Microdot web server after checking for WiFi connectivity.""" 
        # Route definitions
        app.route('/')(self.index) 
        app.route('/submit', methods=['POST'])(self.handle_post)
        app.route('/messages')(self.show_messages)
        app.route('/log')(self.show_log)
        app.route('/system', methods=['POST'])(self.handle_update_trigger)

        wlan = network.WLAN(network.STA_IF) 
        if wlan.isconnected(): 
            ip = wlan.ifconfig()[0] 
            # Start the server to listen on port 80
            await app.start_server(port=80, debug=False)