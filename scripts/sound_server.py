import http.server
import socketserver
import winsound
import sys
import threading
import time

PORT = 8085

class SoundRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/play_sound':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            print("Received sound request! Beeping...")
            try:
                # Play a sound sequence to make it noticeable
                winsound.Beep(1000, 200)
                winsound.Beep(1500, 200)
                winsound.Beep(1000, 200)
            except Exception as e:
                print(f"Error playing sound: {e}")
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        # Suppress default logging to keep terminal clean
        pass

def run_server():
    try:
        with socketserver.TCPServer(("", PORT), SoundRequestHandler) as httpd:
            print(f"Sound server running on port {PORT}...")
            print("Waiting for completion notifications...")
            httpd.serve_forever()
    except OSError as e:
        if e.errno == 10048:
            print(f"Port {PORT} is already in use. Is the server already running?")
        else:
            print(f"Server error: {e}")
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    run_server()

