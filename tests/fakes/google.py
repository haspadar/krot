"""Google's token endpoint, Site Verification, Search Console, the Analytics
Admin API and the Analytics Data API, as far as gsc_site, gsc_access,
ga4_property and ga4_access use them.

The token endpoint is a server of its own: it takes a form rather than JSON, and
it checks the JWT's signature against the service account's public key, so a
test that passes has actually signed with RS256. Tokens it hands out name their
scope and the account they were signed for, and the API fake refuses a token issued for another scope — which is how
a module asking Search Console with the verification token would fail.

The key pair is generated when first needed and never written anywhere.
"""

import base64
import itertools
import json
from urllib.parse import unquote

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from fakes.server import FakeServer

VERIFY_SCOPE = "https://www.googleapis.com/auth/siteverification"
CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/analytics.edit"
USERS_SCOPE = "https://www.googleapis.com/auth/analytics.manage.users"
READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
ADMIN = "predefinedRoles/admin"

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


DEFAULT_REPORT = object()


class FakeGoogle:
    """Site Verification + Search Console + Analytics Admin behind one address."""

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
        self.properties = []
        self.streams = {}
        self.numbers = itertools.count(550407450)
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
        self.accounts = {"301144", "402255"}
        self.page_size = 200
        self.forgets_owners = False
        self.forgets_patches = False
        self.hides_new_properties = False
        # property number -> {account: role}: who may read it, and who may add readers.
        self.access = {}
        # Every grant made through accessBindings, as (property number, user, roles).
        self.bindings = []
        # How many reads a fresh grant is refused for before the Data API sees it.
        self.grant_lag = 0
        self.pending = {}
        self.data_disabled = False
        # What a report answers with 200 instead of a report: a proxy's page, an empty object.
        self.report_replaced_by = DEFAULT_REPORT
        # How many accepted reads after access appears return an incomplete non-empty report.
        self.report_lag = 0
        # A refusal of the report in Google's other words, to tell missing rights from the rest.
        self.refusal = None

    # Seeding.

    def verified(self, domain, owners=None, owned=True):
        self.resources["dns://" + domain] = list(owners or [self.email])
        if owned:
            self.sites["sc-domain:" + domain] = "siteOwner"

    def add_property(self, domain, account="301144", time_zone="Europe/Berlin", currency="EUR", stream=True,
                     owner=None):
        number = str(next(self.numbers))
        # The account that made the property administers it; nobody else sees it.
        self.access[number] = {owner or self.email: ADMIN}
        self.properties.append({"name": "properties/" + number, "parent": "accounts/" + account,
                                "displayName": domain, "timeZone": time_zone, "currencyCode": currency})
        self.streams[number] = []
        if stream:
            self._stream(number, domain)
        return number

    def add_app_stream(self, number):
        """An Android stream: a stream, but no web one, and it has no measurement id."""
        self.streams[number].insert(0, {"name": "properties/%s/dataStreams/%d" % (number, next(self.numbers)),
                                        "type": "ANDROID_APP_DATA_STREAM", "displayName": "app",
                                        "androidAppStreamData": {"packageName": "de.beispiel.app"}})

    def _stream(self, number, domain):
        self.streams[number].append({"name": "properties/%s/dataStreams/%d" % (number, next(self.numbers)),
                                     "type": "WEB_DATA_STREAM", "displayName": domain,
                                     "webStreamData": {"measurementId": "G-%s" % number[-6:],
                                                       "defaultUri": "https://" + domain}})

    # Serving.

    def handle(self, request):
        path = unquote(request.path)
        scope = (VERIFY_SCOPE if path.startswith("/siteVerification") else
                 CONSOLE_SCOPE if path.startswith("/webmasters") else
                 READ_SCOPE if path.startswith("/data/") else
                 USERS_SCOPE if path.endswith("/accessBindings") else ANALYTICS_SCOPE)
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
        if path.startswith("/data/"):
            return self.data(path, email)
        return self.analytics(request, path, email)

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

    def data(self, path, email):
        """Data API: a report is answered to an account that holds a role on the property."""
        if self.data_disabled:
            return refused(403, "Google Analytics Data API has not been used in project 1234 before or it is "
                                "disabled. Enable it by visiting the console.", "PERMISSION_DENIED")
        number = path[len("/data/properties/"):].split(":")[0]
        if self._property(number) is None:
            return refused(404, "Property not found", "NOT_FOUND")
        if self.refusal:
            return refused(403, self.refusal, "PERMISSION_DENIED")
        key = (number, email)
        if self.pending.get(key):
            self.pending[key] -= 1
            return refused(403, "User does not have sufficient permissions for this property.", "PERMISSION_DENIED")
        if email not in self.access.get(number, {}):
            return refused(403, "User does not have sufficient permissions for this property.", "PERMISSION_DENIED")
        if self.report_lag:
            self.report_lag -= 1
            return 200, {"rowCount": 0}
        if self.report_replaced_by is not DEFAULT_REPORT:
            return 200, self.report_replaced_by
        # A property with no data: the headers, and no rows.
        return 200, {"metricHeaders": [{"name": "sessions", "type": "TYPE_INTEGER"}], "rowCount": 0,
                     "kind": "analyticsData#runReport"}

    def grant(self, number, request, email):
        """Access bindings: only an administrator of the property adds a user to it."""
        if self.access.get(number, {}).get(email) != ADMIN:
            return refused(403, "The caller does not have permission", "PERMISSION_DENIED")
        user = request.body["user"]
        if user in self.access[number]:
            return refused(409, "Access binding already exists", "ALREADY_EXISTS")
        self.access[number][user] = request.body["roles"][0]
        self.bindings.append((number, user, list(request.body["roles"])))
        self.pending[(number, user)] = self.grant_lag
        return 200, {"name": "properties/%s/accessBindings/%d" % (number, len(self.bindings)),
                     "user": user, "roles": request.body["roles"]}

    def analytics(self, request, path, email):
        if path == "/properties" and request.method == "GET":
            account = request.query.get("filter", "").replace("parent:accounts/", "")
            if account not in self.accounts:
                return refused(403, "The caller does not have permission", "PERMISSION_DENIED")
            mine = [p for p in self.properties if p["parent"] == "accounts/" + account]
            start = int(request.query.get("pageToken") or 0)
            page = mine[start:start + self.page_size]
            answer = {"properties": page} if page else {}
            if start + self.page_size < len(mine):
                answer["nextPageToken"] = str(start + self.page_size)
            return 200, answer
        if path == "/properties" and request.method == "POST":
            account = request.body["parent"].replace("accounts/", "")
            if account not in self.accounts:
                return refused(403, "The caller does not have permission", "PERMISSION_DENIED")
            number = self.add_property(request.body["displayName"], account, request.body["timeZone"],
                                       request.body["currencyCode"], stream=False, owner=email)
            found = self._property(number)
            if self.hides_new_properties:
                self.properties.remove(found)
            return 200, found
        parts = path.strip("/").split("/")
        number = parts[1] if len(parts) > 1 else ""
        found = self._property(number)
        if found is None:
            return refused(404, "Property not found", "NOT_FOUND")
        if len(parts) == 3 and parts[2] == "accessBindings" and request.method == "POST":
            return self.grant(number, request, email)
        if len(parts) == 2 and request.method == "PATCH":
            if not self.forgets_patches:
                for field in request.query.get("updateMask", "").split(","):
                    found[field] = request.body[field]
            return 200, found
        if len(parts) == 3 and parts[2] == "dataStreams" and request.method == "GET":
            streams = self.streams.get(number, [])
            start = int(request.query.get("pageToken") or 0)
            page = streams[start:start + self.page_size]
            answer = {"dataStreams": page} if page else {}
            if start + self.page_size < len(streams):
                answer["nextPageToken"] = str(start + self.page_size)
            return 200, answer
        if len(parts) == 3 and parts[2] == "dataStreams" and request.method == "POST":
            self._stream(number, request.body["displayName"])
            return 200, self.streams[number][-1]
        return refused(404, "No route %s %s" % (request.method, path), "NOT_FOUND")

    def _property(self, number):
        return next((p for p in self.properties if p["name"] == "properties/" + number), None)
