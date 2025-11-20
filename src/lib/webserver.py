# webserver.py
#
# This module implements the Microdot web server for user interaction,
# handling incoming requests from the web UI and forwarding them to
# the main application event queue.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
import uasyncio as asyncio
import network
from microdot import Microdot, send_file, redirect, Response

app = Microdot()
Response.default_content_type = 'application/json'

# ---------------------------
# webserver class
# ---------------------------
class Webserver:
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
            'emergency': f'{self._base_dir}/emergency.html'
        }

    # ---------------------------
    # routes
    # ---------------------------
    async def index(self, request):
        """Serves the correct HTML file based on the 'page' query parameter."""
        page = request.args.get('page', 'pickup')
        file = self.page_files.get(page, self.page_files['pickup'])
        try:
            return send_file(file, max_age=0)
        except Exception:
            return "404 - File not found", 404

    async def handle_post(self, request):
        """Handles form submissions and puts corresponding events into the queue."""
        form = request.form
        msg_content = form.get('content')
        msg_emergency = form.get('emergency_type')

        if msg_content:
            await self._event_queue.put({
                "type": "PICKUP",
                "value": msg_content,
            })

        elif msg_emergency:
            if msg_emergency.lower() == "staff":
                await self._event_queue.put({
                    "type": "EMERGENCY",
            })
        return redirect('/?page=status')

    async def show_messages(self, request):
        """API endpoint to retrieve the last 5 messages for the status page."""
        msgs = self.state_manager.get_all_messages()
        return {'messages': msgs[-5:]}

    # ---------------------------
    # main loop
    # ---------------------------
    async def run(self):
        """Starts the Microdot web server after checking for WiFi connectivity."""
        app.route('/')(self.index)
        app.route('/submit', methods=['POST'])(self.handle_post)
        app.route('/messages')(self.show_messages)

        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"📡 Webserver running at http://{ip}")
            await app.start_server(port=80, debug=False)
        else:
            print("⚠️ WiFi not connected - Webserver not started.")