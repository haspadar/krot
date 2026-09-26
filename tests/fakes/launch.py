"""Every service a site launch talks to, behind one address, for molecule.

The same fakes the unit tests use, routed by the first path segment:
/cloudflare, /dynadot, /doh/google, /doh/cloudflare, /umami, /google,
/google-token, /yandex, /bing, /uptimerobot, and /site, /site-www for the site
itself. /_state answers what every fake holds, which is what verify.yml reads.
/_run starts a new run of the launch and names its mode; every write a run
sends is kept under it, so verify.yml can tell a dry run that wrote nothing
from one that did. /_open is the project's opening step.

Wired together the way the real ones are, because the launch's most dangerous
decision depends on it: the public resolvers answer what the registrar holds,
and Cloudflare calls a zone active only once the registrar points at its pair.
A launch that wrote records before the delegation was public would therefore
fail here, not only in production. The same goes further down: the site
answers only once its record is in an active zone, and only with 200 once the
project opened it; a search engine verifies only a proof it can find in the
zone.

Run in the scenario's second container:  python3 launch.py <port> <public-url>
The public URL is where the control machine reaches this server; Google's
token endpoint checks the audience against it, as the real one does.
"""

import copy
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes.bing import FakeBing  # noqa: E402
from fakes.cloudflare_rulesets import FakeCloudflareRulesets  # noqa: E402
from fakes.doh import FakeDoh  # noqa: E402
from fakes.dynadot import FakeDynadot  # noqa: E402
from fakes.google import FakeGoogle, FakeTokens, service_account  # noqa: E402
from fakes.server import FakeServer  # noqa: E402
from fakes.umami import FakeUmami  # noqa: E402
from fakes.uptimerobot import FakeUptimeRobot  # noqa: E402
from fakes.yandex import FakeYandex  # noqa: E402

# The domain the scenario launches, bought at the registrar and still parked.
DOMAIN = "krot-launch.de"
PARKING = ["ns1.dyna-ns.net", "ns2.dyna-ns.net"]
# The word the keyword monitor looks for on the home page.
WORD = "Anzeigen"


class Tokens(FakeTokens):
    """Google's token endpoint without a server of its own: the launch one serves it."""

    def __init__(self, uri):
        self.issued = []
        self.refuses = False
        self.fails_with = None
        self._uri = uri

    @property
    def uri(self):
        return self._uri


class Site:
    """The launched site as a visitor and a search engine see it: through Cloudflare.

    Reachable only through a proxied record of an active zone — without one a
    real visitor gets no answer at all, here 530. Behind basic auth until the
    project opens it: roksasex.pl handed Google a sitemap answering 401, and
    Google marked the submission failed within the hour.
    """

    def __init__(self, launch, host):
        self.launch = launch
        self.host = host

    def handle(self, request):
        if not self.launch.proxied(self.host):
            return 530, "error code: 1016", {"Content-Type": "text/plain"}
        headers = {"CF-Ray": "8c0ffee000000000-FRA", "Server": "cloudflare"}
        if not self.launch.opened:
            return 401, "", dict(headers, **{"WWW-Authenticate": 'Basic realm="closed"'})
        if request.path.endswith(".xml"):
            return 200, '<?xml version="1.0"?><urlset/>', dict(headers, **{"Content-Type": "application/xml"})
        return 200, "<html><body>%s</body></html>" % WORD, dict(headers, **{"Content-Type": "text/html"})


class Launch:
    def __init__(self, public_url):
        self.lock = threading.Lock()
        self.dynadot = FakeDynadot()
        self.dynadot.domains[DOMAIN] = list(PARKING)
        self.cloudflare = FakeCloudflareRulesets()
        self.google = FakeGoogle()
        self.tokens = Tokens(public_url + "/google-token/token")
        self.routes = {
            "cloudflare": self.cloudflare,
            "dynadot": self.dynadot,
            "doh": None,
            "umami": FakeUmami(),
            "google": self.google,
            "google-token": self.tokens,
            "yandex": FakeYandex(),
            "bing": FakeBing(),
            "uptimerobot": FakeUptimeRobot(),
            "site": Site(self, DOMAIN),
            "site-www": Site(self, "www." + DOMAIN),
        }
        self.service_account = service_account(self.tokens.uri)
        self.opened = False
        # One entry per run of the launch: its mode and every write it sent.
        self.runs = []

    def zone(self):
        return next((z for z in self.cloudflare.zones if z["name"] == DOMAIN), None)

    def published(self):
        """Records the world can see: those of the zone, once it is active."""
        self.wire()
        zone = self.zone()
        if zone is None or zone["status"] != "active":
            return []
        return [dict(r, content=r["content"].strip('"')) for r in self.cloudflare.zone_records(zone["id"])]

    def proxied(self, host):
        return any(r["type"] == "A" and r["name"] == host and r.get("proxied") for r in self.published())

    def proofs(self):
        """Let each engine verify only what it could find in public DNS."""
        records = self.published()
        texts = {r["content"] for r in records if r["type"] == "TXT" and r["name"] == DOMAIN}
        cnames = {(r["name"], r["content"]) for r in records
                  if r["type"] == "CNAME" and not r.get("proxied")}
        google = "google-site-verification=v-%s" % DOMAIN.split(".")[0]
        self.google.dns_visible_after = 0 if google in texts else 1
        yandex = self.routes["yandex"]
        yandex.fails_verification = any(
            "yandex-verification: %s" % yandex._verification(host)["verification_uin"] not in texts
            for host in yandex.states)
        bing = self.routes["bing"]
        bing.verify_after = 0 if all((s["DnsVerificationCode"], "verify.bing.com") in cnames
                                     for s in bing.sites) else 1

    def note(self, head, request):
        """Keep a write under the run that sent it; reads and sign-ins are not writes."""
        signs_in = head == "google-token" or request.path.endswith("/auth/login")
        # A POST that reads: Site Verification's getToken only hands out the
        # TXT value and records nothing on Google's side.
        asks_token = head == "google" and request.path == "/siteVerification/v1/token"
        # And a GET that writes: Dynadot takes every command as a query.
        sets_ns = head == "dynadot" and request.query.get("command") == "set_ns"
        if (request.method not in ("GET", "HEAD") and not signs_in and not asks_token) or sets_ns:
            if self.runs:
                self.runs[-1]["writes"].append("%s /%s%s" % (request.method, head, request.path))

    def wire(self):
        """What follows from the registrar: resolvers and zone status."""
        delegations = dict(self.dynadot.domains)
        for zone in self.cloudflare.zones:
            held = [host.lower() for host in delegations.get(zone["name"], [])]
            zone["status"] = "active" if sorted(held) == sorted(zone["name_servers"]) else "pending"
        return FakeDoh(delegations)

    def handle(self, request):
        with self.lock:
            segments = request.path.strip("/").split("/")
            head = segments[0]
            if head == "_state":
                return 200, self.state()
            if head == "_setup":
                return 200, {"service_account": self.service_account}
            if head == "_run":
                self.runs.append({"mode": request.body["mode"], "writes": []})
                return 200, {"run": len(self.runs)}
            if head == "_open":
                was_open, self.opened = self.opened, True
                return 200, {"changed": not was_open}
            if head == "doh":
                request.path = "/" + "/".join(segments[2:])
                return self.wire().handle(request)
            app = self.routes.get(head)
            if app is None:
                return 404, {"error": "no fake at /%s" % head}
            request.path = "/" + "/".join(segments[1:])
            self.note(head, request)
            if head == "cloudflare":
                self.wire()
            if head in ("google", "yandex", "bing"):
                self.proofs()
            return app.handle(request)

    def state(self):
        umami, bing, yandex = self.routes["umami"], self.routes["bing"], self.routes["yandex"]
        return copy.deepcopy({
            "registrar": self.dynadot.domains,
            "zones": self.cloudflare.zones,
            "settings": self.cloudflare.settings,
            "records": self.cloudflare.records,
            "rulesets": [dict(r, key=list(k)) for k, r in self.cloudflare.rulesets.items()],
            "certificates": list(self.cloudflare.certificates.values()),
            "umami": umami.websites,
            "google": {"resources": self.google.resources, "sites": self.google.sites,
                       "sitemaps": self.google.sitemaps, "properties": self.google.properties,
                       "streams": self.google.streams},
            "yandex": getattr(yandex, "hosts", None),
            "bing": {"sites": bing.sites, "feeds": bing.feeds},
            "monitors": self.routes["uptimerobot"].monitors,
            "opened": self.opened,
            "runs": self.runs,
        })


def main():
    port, public_url = int(sys.argv[1]), sys.argv[2].rstrip("/")
    server = FakeServer(Launch(public_url), host="0.0.0.0", port=port)
    print("fakes listening on :%d for %s" % (port, public_url), flush=True)
    server.thread.join()


if __name__ == "__main__":
    main()
