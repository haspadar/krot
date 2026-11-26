"""Analytics Admin and Data APIs with scoped tokens and persistent resources."""
import itertools

from fakes.google import FakeGoogle as SearchGoogle, EMAIL, VERIFY_SCOPE, CONSOLE_SCOPE, refused

ANALYTICS_SCOPE = "https://www.googleapis.com/auth/analytics.edit"
READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
USERS_SCOPE = "https://www.googleapis.com/auth/analytics.manage.users"
ADMIN = "predefinedRoles/admin"
VIEWER = "predefinedRoles/viewer"
DEFAULT_REPORT = object()
HUMAN = "operator@example.de"
from urllib.parse import unquote


class FakeAnalytics(SearchGoogle):
    def __init__(self, email=EMAIL):
        super().__init__(email)
        self.properties, self.streams = [], {}
        self.numbers = itertools.count(550407450)
        self.accounts = {"301144", "402255"}
        self.page_size = 200
        self.forgets_patches = False
        self.hides_new_properties = False
        self.access, self.bindings, self.pending = {}, [], {}
        self.grant_lag = 0
        self.data_disabled = False
        self.report_replaced_by = DEFAULT_REPORT
        self.report_lag = 0
        self.refusal = None
        self.account_bindings = {"301144": [{"user": HUMAN, "roles": [ADMIN]}]}
        self.bindings_status = None

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
        if path.startswith("/accounts/") and path.endswith("/accessBindings"):
            if self.bindings_status:
                return refused(self.bindings_status, "Account access denied")
            records = self.account_bindings.get(path.split("/")[2], [])
            start = int(request.query.get("pageToken") or 0)
            answer = {"accessBindings": records[start:start+self.page_size]}
            if start+self.page_size < len(records):
                answer["nextPageToken"] = str(start+self.page_size)
            return 200, answer
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


