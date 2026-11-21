"""The HTTP side of the accounts service."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from accounts import db

DATABASE = "accounts.db"


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not found"})


def main():
    db.connect(DATABASE).close()
    HTTPServer(("localhost", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
