import os
from http.server import SimpleHTTPRequestHandler, HTTPServer
import socketserver

# Dapatkan port dari environment (Railway akan menyediakannya)
PORT = int(os.getenv("PORT", 8000)) # Ubah default ke 8000, 5000 mungkin bermasalah

class MyHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Hello from a basic Python HTTP server on Railway!")

if __name__ == "__main__":
    Handler = MyHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"INFO: Serving basic HTTP server at port {PORT}")
        httpd.serve_forever()
