"""Cloudflare v4 as far as the site-launch modules use it.

Answers in Cloudflare's envelope: `success`, `errors`, `result`, with refusals
as `success: false` — including on HTTP 200 where Cloudflare does that.
"""

import itertools
import re

# The pair is per account, which is the whole reason the zone is created
# before the registrar: the fake hands different accounts different pairs.
PAIRS = {
    None: ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"],
    "acc-gudok": ["cruz.ns.cloudflare.com", "dina.ns.cloudflare.com"],
}

# Made-up tokens: they exist only between a test and this fake, on 127.0.0.1.
TOKEN = "cf-token"  # secret-lint: allow — fake token, never leaves the test process
OTHER_TOKEN = "other-cf-token"  # secret-lint: allow — the fake's side of a token mismatch

DEFAULT_SETTINGS = {"ssl": "full", "always_use_https": "off", "browser_cache_ttl": 14400,
                    "tls_client_auth": "off"}


def ok(result):
    return 200, {"success": True, "errors": [], "messages": [], "result": result}


def refused(status, message, code=1000):
    return status, {"success": False, "errors": [{"code": code, "message": message}], "result": None}


class FakeCloudflare:
    def __init__(self, token=TOKEN):
        self.token = token
        self.zones = []
        self.settings = {}
        self.certificates = {}
        self.records = []
        self.ids = itertools.count(1)
        # Knobs for the failures worth testing.
        self.forgets_settings = False
        self.hides_new_zones = False
        # Takes a record write and keeps nothing.
        self.forgets_records = False
        # Reads a certificate back as something other than what was issued.
        self.certificates_drift = False

    def add_zone(self, name, account=None, status="active"):
        zone = {"id": "zone-%d" % next(self.ids), "name": name, "status": status,
                "account": {"id": account}, "name_servers": list(PAIRS.get(account, PAIRS[None]))}
        self.zones.append(zone)
        self.settings[zone["id"]] = dict(DEFAULT_SETTINGS)
        return zone

    def add_record(self, zone_id, kind, name, content, proxied=None):
        record = {"id": "rec-%d" % next(self.ids), "zone_id": zone_id, "type": kind, "name": name,
                  "content": content, "ttl": 1}
        if proxied is not None:
            record["proxied"] = proxied
        self.records.append(record)
        return record

    def zone_records(self, zone_id):
        return [r for r in self.records if r["zone_id"] == zone_id]

    def handle(self, request):
        if request.headers.get("Authorization") != "Bearer " + self.token:
            return refused(403, "Authentication error", 10000)
        path, method = request.path, request.method

        if path == "/zones" and method == "GET":
            account = request.query.get("account.id")
            return ok([z for z in self.zones if z["name"] == request.query.get("name")
                       and (account is None or z["account"]["id"] == account)])
        if path == "/zones" and method == "POST":
            name = request.body["name"]
            account = (request.body.get("account") or {}).get("id")
            if any(z["name"] == name and z["account"]["id"] == account for z in self.zones):
                return refused(400, "A zone with this name already exists", 1061)
            zone = self.add_zone(name, account, status="pending")
            if self.hides_new_zones:
                self.zones.remove(zone)
            return ok(zone)

        every = re.match(r"^/zones/([^/]+)/settings$", path)
        if every and method == "GET":
            if every.group(1) not in self.settings:
                return refused(404, "Invalid zone identifier", 7003)
            return ok([{"id": k, "value": v, "editable": True} for k, v in self.settings[every.group(1)].items()])
        setting = re.match(r"^/zones/([^/]+)/settings/([^/]+)$", path)
        if setting:
            zone, name = setting.groups()
            if zone not in self.settings:
                return refused(404, "Invalid zone identifier", 7003)
            if name not in DEFAULT_SETTINGS:
                return refused(400, "Undefined zone setting", 1006)
            if method == "PATCH" and not self.forgets_settings:
                self.settings[zone][name] = request.body["value"]
            return ok({"id": name, "value": self.settings[zone].get(name), "editable": True})

        listing = re.match(r"^/zones/([^/]+)/dns_records$", path)
        if listing and method == "GET":
            query = request.query
            return ok([r for r in self.zone_records(listing.group(1))
                       if r["type"] == query.get("type", r["type"]) and r["name"] == query.get("name", r["name"])])
        if listing and method == "POST":
            body = request.body
            if body["type"] in ("A", "AAAA", "CNAME") and any(
                    r["type"] == body["type"] and r["name"] == body["name"] for r in self.zone_records(listing.group(1))):
                return refused(400, "An identical record already exists.", 81058)
            if self.forgets_records:
                return ok(dict(body, id="rec-lost"))
            return ok(self.add_record(listing.group(1), body["type"], body["name"], body["content"], body.get("proxied")))
        one = re.match(r"^/zones/([^/]+)/dns_records/([^/]+)$", path)
        if one and method == "PUT":
            record = next((r for r in self.records if r["id"] == one.group(2)), None)
            if record is None:
                return refused(404, "Record not found", 81044)
            if not self.forgets_records:
                record.update(dict((k, v) for k, v in request.body.items() if k in ("type", "name", "content", "proxied", "ttl")))
            return ok(record)

        if path == "/certificates" and method == "POST":
            if "BEGIN CERTIFICATE REQUEST" not in request.body.get("csr", ""):
                return refused(400, "Invalid CSR", 1010)
            number = next(self.ids)
            certificate = {"id": "cert-%d" % number, "hostnames": request.body["hostnames"],
                           "certificate": "-----BEGIN CERTIFICATE-----\nfake-%d\n-----END CERTIFICATE-----\n" % number,
                           "expires_on": "2041-09-26 00:00:00 +0000 UTC",
                           "request_type": request.body["request_type"]}
            self.certificates[certificate["id"]] = certificate
            return ok(certificate)
        held = re.match(r"^/certificates/([^/]+)$", path)
        if held and method == "GET":
            if held.group(1) not in self.certificates:
                return refused(404, "Certificate not found", 1001)
            # True reads back another certificate, None reads back a null one.
            if self.certificates_drift is not False:
                other = "-----BEGIN CERTIFICATE-----\nother\n" if self.certificates_drift else None
                return ok(dict(self.certificates[held.group(1)], certificate=other))
            return ok(self.certificates[held.group(1)])

        return refused(404, "No route for %s %s" % (method, path), 7000)
