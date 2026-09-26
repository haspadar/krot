"""A DNS-over-HTTPS JSON resolver (dns.google / cloudflare-dns style), NS only.

One fake per resolver, so a test can make the two disagree the way two real
caches do while a delegation spreads.
"""

NOERROR = 0
SERVFAIL = 2
NXDOMAIN = 3


class FakeDoh:
    def __init__(self, delegations=None):
        # Domain to the nameservers this resolver currently reports.
        self.delegations = dict(delegations or {})
        # Status to answer with instead of looking anything up (SERVFAIL, say).
        self.status = None

    def handle(self, request):
        domain = request.query.get("name", "")
        if request.query.get("type") != "NS":
            return 400, {"Status": 1, "Comment": "only NS here"}
        if self.status is not None:
            return 200, {"Status": self.status, "Question": [{"name": domain + ".", "type": 2}]}
        if domain not in self.delegations:
            return 200, {"Status": NXDOMAIN, "Question": [{"name": domain + ".", "type": 2}]}
        return 200, {
            "Status": NOERROR,
            "Question": [{"name": domain + ".", "type": 2}],
            # Real resolvers answer with the trailing dot, and not always in lower case.
            "Answer": [{"name": domain + ".", "type": 2, "TTL": 3600, "data": host + "."}
                       for host in self.delegations[domain]],
        }
