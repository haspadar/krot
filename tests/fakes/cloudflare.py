"""Cloudflare v4 as far as the site-launch modules use it.

Answers in Cloudflare's envelope: `success`, `errors`, `result`, with refusals
as `success: false` — including on HTTP 200 where Cloudflare does that.
"""

import copy
import itertools
import re

# The pair is per account, which is the whole reason the zone is created
# before the registrar: the fake hands different accounts different pairs.
PAIRS = {
    None: ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"],
    "acc-second": ["cruz.ns.cloudflare.com", "dina.ns.cloudflare.com"],
}

# Made-up tokens: they exist only between a test and this fake, on 127.0.0.1.
TOKEN = "cf-token"  # secret-lint: allow — fake token, never leaves the test process
OTHER_TOKEN = "other-cf-token"  # secret-lint: allow — the fake's side of a token mismatch

# The account a zone made without one is in: Cloudflare puts every zone in some account.
DEFAULT_ACCOUNT = "acc-main"

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
        # Web Analytics records, as Cloudflare lists them under an account.
        self.rum = []
        # A zone gets its record when it is added, in the lite form that leaves the
        # script out of pages for visitors from the EU — the case this is here for.
        self.rum_on_new_zone = True
        self.rum_creates_lite = True
        # Takes a Web Analytics write and keeps nothing.
        self.forgets_rum = False
        # A token without the right for Web Analytics: every answer is a 403.
        self.rum_forbidden = False
        # The largest page a list is answered with, whatever page size was asked.
        self.rum_page_cap = 100
        # Whether a list says how many pages it has.
        self.rum_counts_pages = True

    def add_zone(self, name, account=None, status="active"):
        zone = {"id": "zone-%d" % next(self.ids), "name": name, "status": status,
                "account": {"id": account}, "name_servers": list(PAIRS.get(account, PAIRS[None]))}
        self.zones.append(zone)
        self.settings[zone["id"]] = dict(DEFAULT_SETTINGS)
        if self.rum_on_new_zone:
            self.add_rum(zone, lite=self.rum_creates_lite)
        return zone

    def add_rum(self, zone, lite=False, enabled=True, auto_install=True):
        entry = {"site_tag": "tag-%d" % next(self.ids), "auto_install": auto_install,
                 "ruleset": {"zone_tag": zone["id"], "zone_name": zone["name"], "enabled": enabled, "lite": lite}}
        self.rum.append(entry)
        return entry

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

        if method == "GET" and re.match(r"^/zones/[^/]+$", path):
            zone = next((z for z in self.zones if z["id"] == path.split("/")[2]), None)
            if zone is None:
                return refused(404, "Invalid zone identifier", 7003)
            return ok(dict(zone, account={"id": zone["account"]["id"] or DEFAULT_ACCOUNT}))

        rum = self.handle_rum(request)
        if rum is not None:
            return rum

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

    def handle_rum(self, request):
        """Web Analytics under /accounts, or None for a path that is not one."""
        path, method = request.path, request.method
        found = re.match(r"^/accounts/([^/]+)/rum/site_info(/list|/[^/]+)?$", path)
        if not found:
            return None
        if self.rum_forbidden:
            return refused(403, "Authentication error", 10000)
        tail = found.group(2)

        if tail == "/list" and method == "GET":
            size = min(int(request.query.get("per_page", 10)), self.rum_page_cap)
            page = int(request.query.get("page", 1))
            answer = ok(copy.deepcopy(self.rum[(page - 1) * size:page * size]))
            if self.rum_counts_pages:
                answer[1]["result_info"] = {"page": page, "per_page": size, "total_count": len(self.rum),
                                            "total_pages": max(1, -(-len(self.rum) // size))}
            return answer
        if tail is None and method == "POST":
            zone = next((z for z in self.zones if z["id"] == request.body.get("zone_tag")), None)
            if zone is None:
                return refused(400, "zone_tag is not a zone of this account", 10001)
            if self.forgets_rum:
                return ok({"site_tag": "tag-lost"})
            entry = self.add_rum(zone, lite=self.rum_creates_lite, auto_install=bool(request.body.get("auto_install")))
            return ok(entry)
        if tail and method == "PUT":
            entry = next((e for e in self.rum if e["site_tag"] == tail[1:]), None)
            if entry is None:
                return refused(404, "site not found", 10002)
            if not self.forgets_rum:
                body = request.body
                entry["auto_install"] = body["auto_install"]
                entry["ruleset"].update(enabled=body["enabled"], lite=body["lite"])
            return ok(entry)
        return refused(404, "No route for %s %s" % (method, path), 7000)
