"""A real HTTP server in a thread, answering through a fake of one service.

Real rather than a patched open_url, so a test sees what the module actually
sent — method, path, query, body, headers — and the module goes through the
same code path it takes in production. The same fakes are meant to serve the
molecule scenario from a container.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit


class Request:
    def __init__(self, method, path, query, body, headers):
        self.method = method
        self.path = path
        self.query = query
        self.body = body
        self.headers = headers

    def writes(self):
        return self.method != "GET"

    def __repr__(self):
        return "%s %s" % (self.method, self.path)


def parsed(raw, kind):
    if not raw:
        return None
    if kind.startswith("application/x-www-form-urlencoded"):
        return dict(parse_qsl(raw.decode()))
    return json.loads(raw)


class FakeServer:
    """Serves `app.handle(request) -> (status, body)` on a free local port.

    `outages` is a queue of failures served before the app sees anything: an
    int answers with that status, "drop" closes the connection unanswered,
    "html" answers 200 with a page that is not JSON, and "lost" lets the app
    handle the request — the write happens — and then answers 502, the way a
    proxy does when the service is slow to reply. None serves the request
    normally, to aim a failure at a later one; a (status, headers) pair answers
    with those headers, and a third element is the raw body.
    """

    def __init__(self, app):
        self.app = app
        self.requests = []
        self.outages = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                request = Request(self.command, parts.path, dict(parse_qsl(parts.query)),
                                  parsed(raw, self.headers.get("Content-Type", "")), dict(self.headers))
                server.requests.append(request)
                outage = server.outages.pop(0) if server.outages else None
                if outage is not None:
                    if outage == "drop":
                        self.close_connection = True
                        self.connection.close()
                        return
                    if outage == "html":
                        return self.answer(200, b"<html>captive portal</html>")
                    if outage == "lost":
                        server.app.handle(request)
                        return self.answer(502, b"")
                    if isinstance(outage, tuple):
                        page = outage[2] if len(outage) > 2 else b""
                        return self.answer(outage[0], page, outage[1])
                    return self.answer(outage, b"")
                status, body = server.app.handle(request)
                self.answer(status, json.dumps(body).encode() if body is not None else b"")

            def answer(self, status, payload, headers=None):
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_any

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, args=(0.01,), daemon=True)
        self.thread.start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def writes(self):
        return [request for request in self.requests if request.writes()]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
