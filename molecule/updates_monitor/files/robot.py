"""Run the shared UptimeRobot fake for the actual delegated role task."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qsl
from uptimerobot import FakeUptimeRobot

robot = FakeUptimeRobot()


class Handler(BaseHTTPRequestHandler):
    def request(self):
        url = urlsplit(self.path)
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or '{}')
        status, data = robot.handle(SimpleNamespace(path=url.path, method=self.command,
                                                    query=dict(parse_qsl(url.query)),
                                                    body=body, headers=self.headers))
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    do_GET = request
    do_POST = request
    do_PATCH = request

    def log_message(self, *args):
        pass


HTTPServer(('0.0.0.0', 47189), Handler).serve_forever()
