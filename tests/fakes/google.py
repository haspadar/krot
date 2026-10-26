"""Google's token endpoint, Site Verification and Search Console, as far as
gsc_site and gsc_access use them.

The token endpoint is a server of its own: it takes a form rather than JSON, and
it checks the JWT's signature against the service account's public key, so a
test that passes has actually signed with RS256. Tokens it hands out name their
scope and the account they were signed for, and the API fake refuses a token issued for another scope — which is how
a module asking Search Console with the verification token would fail.

The key pair is generated when first needed and never written anywhere.
"""

import base64
import json
from urllib.parse import unquote

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from fakes.server import FakeServer

VERIFY_SCOPE = "https://www.googleapis.com/auth/siteverification"
CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters"
EMAIL = "launcher@krot-units.iam.gserviceaccount.com"

_KEY = []


def key_pair():
    if not _KEY:
        _KEY.append(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    return _KEY[0]


def service_account(token_uri, email=EMAIL):
    """A service account key file as Google issues it, for a key made in memory."""
    pem = key_pair().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption()).decode()
    return json.dumps({"type": "service_account", "client_email": email, "token_uri": token_uri,
                       "private_key": pem})


def unpadded(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class FakeTokens:
    """Google's OAuth endpoint: the signature is checked, the scope named in what it hands out."""

    def __init__(self):
        self.issued = []
        self.refuses = False
        # An HTTP status to answer instead of a token, for a Google-side outage.
        self.fails_with = None
        self.server = FakeServer(self)

    @property
    def uri(self):
        return self.server.url + "/token"

    def handle(self, request):
        form = request.body or {}
        if self.fails_with:
            return self.fails_with, {"error": "internal_failure"}
        if self.refuses:
            return 400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."}
        if form.get("grant_type") != "urn:ietf:params:oauth:grant-type:jwt-bearer":
            return 400, {"error": "unsupported_grant_type", "error_description": "Invalid grant_type"}
        header, body, signature = form.get("assertion", "..").split(".")
        try:
            key_pair().public_key().verify(unpadded(signature), (header + "." + body).encode(),
                                           padding.PKCS1v15(), hashes.SHA256())
        except Exception:
            return 400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."}
        claim = json.loads(unpadded(body))
        if json.loads(unpadded(header)).get("alg") != "RS256" or claim.get("aud") != self.uri:
            return 400, {"error": "invalid_grant", "error_description": "Invalid JWT: aud or alg"}
        self.issued.append(claim["scope"])
        return 200, {"access_token": "tok|%s|%d|%s" % (claim["scope"], len(self.issued), claim.get("iss")),
                     "expires_in": 3599, "token_type": "Bearer"}

    def close(self):
        self.server.close()


def refused(status, message, state="INVALID_ARGUMENT"):
    return status, {"error": {"code": status, "message": message, "status": state}}


class FakeGoogle:
    """Site Verification + Search Console behind one address."""

    def __init__(self, email=EMAIL):
        self.email = email
        # dns://<domain> -> owners, for domains the account has verified.
        self.resources = {}
        # sc-domain:<domain> -> permissionLevel, in the launching account's Search Console.
        self.sites = {}
        # The same for every other key: account -> {sc-domain:<domain> -> permissionLevel}.
        self.others = {}
        # How many reads of a property another key added still miss it, as Search Console
        # does while an ownership granted through Site Verification propagates.
        self.owner_lag = 0
        # sites.add answered 403 this many times before it is accepted.
        self.add_refusals = 0
        # What sites.get answers for a property the account does not have: 404, or the 403
        # searchAnalytics answers in the same case.
        self.unknown_site_status = 404
        # sc-domain:<domain> -> submitted sitemap URLs, and every submission.
        self.sitemaps = {}
        self.submissions = []
        # Knobs for the failures worth testing.
        self.dns_visible_after = 0
        self.permission_lag = 0
        self.owners_broken = False
        # Owner reads that answer normally before the list comes back empty.
        self.owners_vanish_after = None
        # What a resource this account does not own answers: 404, or 403 as Google often does.
        self.unowned_status = 404
        # A status for the verification call alone, the token request still working.
        self.verification_refused_with = None
        self.disabled_scopes = set()
        # The same for one key alone: account -> scopes switched off in that key's project, as
        # when the launching and the collecting key live in different Cloud projects.
        self.disabled_for = {}
    # Seeding.

    def verified(self, domain, owners=None, owned=True):
        self.resources["dns://" + domain] = list(owners or [self.email])
        if owned:
            self.sites["sc-domain:" + domain] = "siteOwner"

    # Serving.

    def handle(self, request):
        path = unquote(request.path)
        if not path.startswith(("/siteVerification", "/webmasters")):
            return refused(404, "No route %s %s" % (request.method, path), "NOT_FOUND")
        scope = VERIFY_SCOPE if path.startswith("/siteVerification") else CONSOLE_SCOPE
        bearer = request.headers.get("Authorization", "")
        if not bearer.startswith("Bearer tok|%s|" % scope):
            return refused(401, "Request had invalid authentication credentials.", "UNAUTHENTICATED")
        # The account the token was signed for: the last field of the token.
        email = bearer.split("|")[-1]
        if scope in self.disabled_scopes or scope in self.disabled_for.get(email, ()):
            return refused(403, "The API has not been used in project 1234 before or it is disabled.",
                           "PERMISSION_DENIED")
        if path.startswith("/siteVerification"):
            return self.verification(request, path, email)
        if path.startswith("/webmasters"):
            return self.console(request, path, email)
        return refused(404, "No route %s %s" % (request.method, path), "NOT_FOUND")

    def account_sites(self, email):
        return self.sites if email == self.email else self.others.setdefault(email, {})

    def verification(self, request, path, email):
        if path == "/siteVerification/v1/token" and request.method == "POST":
            domain = request.body["site"]["identifier"]
            return 200, {"method": "DNS_TXT", "token": "google-site-verification=v-%s" % domain.split(".")[0]}
        if path == "/siteVerification/v1/webResource" and request.method == "POST":
            if self.verification_refused_with:
                return refused(self.verification_refused_with, "The caller does not have permission", "PERMISSION_DENIED")
            if request.query.get("verificationMethod") != "DNS_TXT":
                return refused(400, "Invalid verification method")
            if self.dns_visible_after:
                self.dns_visible_after -= 1
                return refused(400, "The necessary verification token could not be found on your site.")
            domain = request.body["site"]["identifier"]
            owners = self.resources.setdefault("dns://" + domain, [])
            if email not in owners:
                owners.append(email)
            return 200, {"id": "dns://" + domain, "site": request.body["site"], "owners": owners}
        if path.startswith("/siteVerification/v1/webResource/"):
            resource = path[len("/siteVerification/v1/webResource/"):]
            if resource not in self.resources or email not in self.resources[resource]:
                return refused(self.unowned_status, "You are not an owner of this site.", "NOT_FOUND")
            if request.method == "PUT":
                if not self.forgets_owners:
                    self.resources[resource] = list(request.body["owners"])
            if request.method == "GET" and self.owners_vanish_after is not None:
                if self.owners_vanish_after == 0:
                    self.owners_broken = True
                self.owners_vanish_after -= 1
            owners = [] if self.owners_broken else self.resources[resource]
            return 200, {"id": resource, "site": {"type": "INET_DOMAIN", "identifier": resource[6:]},
                         "owners": owners}
        return refused(404, "No route %s %s" % (request.method, path), "NOT_FOUND")

    def console(self, request, path, email):
        sites = self.account_sites(email)
        if path == "/webmasters/v3/sites" and request.method == "GET":
            if self.permission_lag:
                self.permission_lag -= 1
                return 200, {"siteEntry": [{"siteUrl": s, "permissionLevel": "siteUnverifiedUser"}
                                           for s in sites]}
            # An account with no sites answers {} rather than an empty list.
            if not sites:
                return 200, {}
            return 200, {"siteEntry": [{"siteUrl": s, "permissionLevel": p} for s, p in sites.items()]}
        prefix = "/webmasters/v3/sites/"
        rest = path[len(prefix):]
        site, _, sitemap = rest.partition("/sitemaps/")
        if not sitemap and request.method == "PUT":
            if email != self.email and self.add_refusals:
                self.add_refusals -= 1
                return refused(403, "User does not have sufficient permission for site.", "PERMISSION_DENIED")
            verified = email in self.resources.get("dns://" + site[len("sc-domain:"):], [])
            sites[site] = "siteOwner" if verified else "siteUnverifiedUser"
            return 204, None
        # sites.get: a property is known only to an account that added it, in the words Google
        # answered a key without rights with on 2026-10-22.
        if not sitemap and request.method == "GET":
            if site not in sites or (email != self.email and self.owner_lag):
                if site in sites:
                    self.owner_lag -= 1
                if self.unknown_site_status == 403:
                    return refused(403, "User does not have sufficient permission for site '%s'." % site,
                                   "PERMISSION_DENIED")
                return refused(404, "'%s' is not a verified Search Console site in this account." % site,
                               "NOT_FOUND")
            return 200, {"siteUrl": site, "permissionLevel": sites[site]}
        if sitemap and request.method == "PUT":
            if sites.get(site) != "siteOwner":
                return refused(403, "User does not have sufficient permission for site.", "PERMISSION_DENIED")
            self.submissions.append(sitemap)
            listed = self.sitemaps.setdefault(site, [])
            if sitemap not in listed:
                listed.append(sitemap)
            return 204, None
        if sitemap and request.method == "GET":
            if sitemap not in self.sitemaps.get(site, []):
                return refused(404, "Requested entity was not found.", "NOT_FOUND")
            return 200, {"path": sitemap, "isPending": True}
        return refused(404, "No route %s %s" % (request.method, path), "NOT_FOUND")
