"""Dynadot's api3.json as far as dynadot_ns uses it: get_ns and set_ns.

Answers 200 whatever happens, with the result code in the body — the way
Dynadot does, which is why the module reads the body and not the status.
"""

# Made-up key: it exists only between a test and this fake, on 127.0.0.1.
KEY = "dynadot-key"  # secret-lint: allow — fake key, never leaves the test process


class FakeDynadot:
    def __init__(self, key=KEY):
        self.key = key
        # Domain to the nameservers the account holds for it.
        self.domains = {}
        # Domains Dynadot answers "unsupported domain type" for (a .kz, say).
        self.unsupported = set()
        # Accepts set_ns but keeps the old nameservers.
        self.ignores_writes = False
        # Refuses set_ns with this reason.
        self.refuses_writes = None

    def handle(self, request):
        query = request.query
        if query.get("key") != self.key:
            return 200, {"Response": {"ResponseCode": "-1", "Error": "invalid key"}}
        command, domain = query.get("command"), query.get("domain", "")

        if command == "get_ns":
            if domain in self.unsupported:
                return 200, {"GetNsResponse": {"ResponseCode": "-1", "Status": "error", "Error": "unsupported domain type"}}
            if domain not in self.domains:
                return 200, {"GetNsResponse": {"ResponseCode": "-1", "Status": "error",
                                               "Error": "could not find domain in your account"}}
            hosts = dict(("Host%d" % i, host) for i, host in enumerate(self.domains[domain]))
            return 200, {"GetNsResponse": {"ResponseCode": "0", "Status": "success", "NsContent": hosts}}

        if command == "set_ns":
            if self.refuses_writes:
                return 200, {"SetNsResponse": {"ResponseCode": "-1", "Status": "error", "Error": self.refuses_writes}}
            if domain not in self.domains:
                return 200, {"SetNsResponse": {"ResponseCode": "-1", "Status": "error",
                                               "Error": "could not find domain in your account"}}
            hosts = [query[name] for name in sorted(query) if name.startswith("ns")]
            if not self.ignores_writes:
                self.domains[domain] = hosts
            return 200, {"SetNsResponse": {"ResponseCode": "0", "Status": "success"}}

        return 200, {"Response": {"ResponseCode": "-1", "Error": "unknown command %s" % command}}
