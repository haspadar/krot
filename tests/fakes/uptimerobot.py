"""UptimeRobot v3 as far as uptimerobot_monitor uses it.

Pages its lists the way v3 does: no total, only a `nextLink` while more is
left, built from the address the request came to.
"""

import itertools
import re

# Made-up key: it exists only between a test and this fake, on 127.0.0.1.
KEY = "ur-key"  # secret-lint: allow — fake key, never leaves the test process


class FakeUptimeRobot:
    def __init__(self, key=KEY):
        self.key = key
        self.monitors = []
        self.contacts = [{"id": 101, "status": "Active", "type": "Email"}]
        self.ids = itertools.count(900)
        self.page_size = 50

    def add_monitor(self, name, type_="HTTP", keyword=None, contacts=True):
        monitor = {"id": next(self.ids), "friendlyName": name, "type": type_,
                   "url": "https://%s/" % name.split(" ")[0],
                   "assignedAlertContacts": [{"alertContactId": "101"}] if contacts else []}
        if keyword is not None:
            monitor.update(keywordValue=keyword, keywordType="ALERT_NOT_EXISTS", keywordCaseType="CaseSensitive")
        self.monitors.append(monitor)
        return monitor

    def page(self, request, entries):
        start = int(request.query.get("cursor", 0))
        answer = {"data": entries[start:start + self.page_size]}
        if start + self.page_size < len(entries):
            answer["nextLink"] = "http://%s%s?limit=50&cursor=%d" % (
                request.headers["Host"], request.path, start + self.page_size)
        return 200, answer

    def handle(self, request):
        if request.headers.get("Authorization") != "Bearer " + self.key:
            return 401, {"message": "Unauthorized"}
        path, method = request.path, request.method

        if path == "/monitors" and method == "GET":
            return self.page(request, self.monitors)
        if path == "/alert-contacts" and method == "GET":
            return self.page(request, self.contacts)
        if path == "/monitors" and method == "POST":
            body = dict(request.body, id=next(self.ids))
            self.monitors.append(body)
            return 201, body
        one = re.match(r"^/monitors/(\d+)$", path)
        if one:
            monitor = next((m for m in self.monitors if str(m["id"]) == one.group(1)), None)
            if monitor is None:
                return 404, {"message": "Monitor not found"}
            if method == "PATCH":
                if "type" in request.body and request.body["type"] != monitor["type"]:
                    return 400, {"message": "Monitor type cannot be changed"}
                monitor.update(request.body)
                return 200, monitor
            if method == "DELETE":
                self.monitors.remove(monitor)
                return 200, None
        return 404, {"message": "No route for %s %s" % (method, path)}


class FakePage:
    """The watched site's front page."""

    def __init__(self, text):
        self.text = text

    def handle(self, request):
        return 200, self.text
