"""Every service a site launch talks to, behind one address, for molecule.

The same fakes the unit tests use, routed by the first path segment:
/cloudflare, /dynadot, /doh/google, /doh/cloudflare, /umami, /google,
/google-token, /yandex, /bing, /uptimerobot, and /site, /site-www for the site
itself. /_state answers what every fake holds, which is what verify.yml reads.

Wired together the way the real ones are, because the launch's most dangerous
decision depends on it: the public resolvers answer what the registrar holds,
and Cloudflare calls a zone active only once the registrar points at its pair.
A launch that wrote records before the delegation was public would therefore
fail here, not only in production.

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
    """The launched site as a visitor and a search engine see it: through Cloudflare."""

    def handle(self, request):
        headers = {"CF-Ray": "8c0ffee000000000-FRA", "Server": "cloudflare"}
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
            "site": Site(),
            "site-www": Site(),
        }
        self.service_account = service_account(self.tokens.uri)

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
            if head == "doh":
                request.path = "/" + "/".join(segments[2:])
                return self.wire().handle(request)
            app = self.routes.get(head)
            if app is None:
                return 404, {"error": "no fake at /%s" % head}
            request.path = "/" + "/".join(segments[1:])
            if head == "cloudflare":
                self.wire()
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
        })


def main():
    port, public_url = int(sys.argv[1]), sys.argv[2].rstrip("/")
    server = FakeServer(Launch(public_url), host="0.0.0.0", port=port)
    print("fakes listening on :%d for %s" % (port, public_url), flush=True)
    server.thread.join()


if __name__ == "__main__":
    main()
