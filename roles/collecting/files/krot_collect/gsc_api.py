"""Bounded, finalized Search Console requests using a read-only service account."""

import json
import math
import re
import time
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from krot_collect.google_jwt import GRANT_TYPE, TOKEN_URI, ServiceAccountKey

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
ROW_LIMIT = 25000
DIMENSIONS = {"query": ["query", "country", "device"], "page": ["page"], "page_query": ["page", "query"]}


class GscError(Exception):
    """Stable, credential-free failure information suitable for persistent attempts."""

    def __init__(self, status, reason):
        self.status = status
        self.reason = reason
        super().__init__("GSC HTTP %s: %s" % (status, reason))


class NoRedirect(HTTPRedirectHandler):
    # A bearer token must never ride to a redirect destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_call(method, url, headers=None, body=None, form=None):
    """Return status, decoded JSON and headers; never include raw bodies in errors."""
    headers = dict(headers or {})
    payload = None
    if form is not None:
        payload = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=payload, headers=headers, method=method)
    try:
        answer = build_opener(NoRedirect()).open(request, timeout=30)
    except HTTPError as error:
        answer = error
    except (URLError, OSError, ValueError):
        raise GscError(0, "transport_failure") from None
    try:
        with answer:
            status = answer.code
            response_headers = dict(answer.headers.items())
            raw = answer.read()
    except Exception:
        raise GscError(0, "transport_failure") from None
    try:
        decoded = json.loads(raw)
    except (ValueError, UnicodeError):
        # Keep HTTP failures retryable even if Google's proxy answers with HTML.
        if status < 200 or status >= 300:
            decoded = None
        else:
            raise GscError(status, "invalid_json") from None
    return status, decoded, response_headers


def iso_day(value):
    if type(value) is date:
        return value.isoformat()
    if not isinstance(value, str):
        raise GscError(0, "invalid_date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise GscError(0, "invalid_date") from None
    if parsed.isoformat() != value:
        raise GscError(0, "invalid_date")
    return value


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def error_reason(answer):
    # Never persist Google's free-form message/error_description: it may echo
    # an assertion, credential or response body. Keep only structured identifiers.
    if isinstance(answer, dict):
        error = answer.get("error")
        if isinstance(error, dict):
            errors = error.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                candidate = errors[0].get("reason")
            else:
                candidate = error.get("status")
        else:
            candidate = error
        allowed = {"invalid_grant", "invalid_client", "invalid_request", "unauthorized_client",
                   "access_denied", "insufficientPermissions", "forbidden", "notFound",
                   "authError", "rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded",
                   "backendError", "internalError", "badRequest", "PERMISSION_DENIED",
                   "UNAUTHENTICATED", "NOT_FOUND", "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE"}
        if isinstance(candidate, str) and candidate in allowed:
            return candidate
    return "request_failed"


class Client:
    def __init__(self, key_json, call=None, clock=time.time, sleep=time.sleep,
                 key_factory=ServiceAccountKey, max_pages=4, retries=3):
        if type(max_pages) is not int or max_pages < 1 or max_pages > 100:
            raise ValueError("max_pages must be between 1 and 100")
        if type(retries) is not int or retries < 0 or retries > 10:
            raise ValueError("retries must be between 0 and 10")
        try:
            self.key = key_factory(key_json)
        except Exception:
            raise GscError(0, "invalid_service_account") from None
        self.call = call or http_call
        self.clock, self.sleep = clock, sleep
        self.max_pages, self.retries = max_pages, retries
        self.token, self.token_until = None, 0

    def _request(self, url, headers=None, body=None, form=None):
        for retry in range(self.retries + 1):
            try:
                status, answer, response_headers = self.call("POST", url, headers=headers, body=body, form=form)
            except GscError:
                raise
            except Exception:
                raise GscError(0, "transport_failure") from None
            if status == 200:
                if not isinstance(answer, dict) or "error" in answer:
                    raise GscError(status, "invalid_response")
                return answer
            if (status == 429 or 500 <= status <= 599) and retry < self.retries:
                delay = min(2 ** retry, 60)
                retry_after = next((v for k, v in (response_headers or {}).items()
                                    if k.lower() == "retry-after"), None)
                if retry_after is not None:
                    try:
                        delay = float(retry_after)
                    except (ValueError, TypeError):
                        try:
                            delay = parsedate_to_datetime(retry_after).timestamp() - self.clock()
                        except (ValueError, TypeError, OverflowError):
                            pass
                if not math.isfinite(delay):
                    delay = 60
                self.sleep(max(0, min(delay, 60)))
                continue
            raise GscError(status, error_reason(answer))

    def _token(self):
        if self.token is not None and self.clock() < self.token_until:
            return self.token
        now = self.clock()
        try:
            assertion = self.key.assertion(SCOPE, TOKEN_URI, now=int(now))
        except Exception:
            raise GscError(0, "invalid_service_account") from None
        answer = self._request(TOKEN_URI, form={"grant_type": GRANT_TYPE, "assertion": assertion})
        token = answer.get("access_token")  # secret-lint: allow — runtime API field, no literal credential
        expires = answer.get("expires_in", 3600)
        if (not isinstance(token, str) or not token or any(c.isspace() for c in token)
                or not finite_number(expires) or expires <= 0):
            raise GscError(200, "invalid_token_response")
        self.token, self.token_until = token, now + min(3000, expires)
        return token

    def _url(self, property):
        if not isinstance(property, str) or not property or any(c.isspace() or ord(c) < 32 for c in property):
            raise GscError(0, "invalid_property")
        if property.startswith("sc-domain:"):
            if not property[len("sc-domain:"):] or "/" in property[len("sc-domain:"):]:
                raise GscError(0, "invalid_property")
        else:
            try:
                parsed = urlsplit(property)
                valid = parsed.scheme in ("https", "http") and parsed.netloc and not parsed.username and not parsed.password
            except ValueError:
                valid = False
            if not valid:
                raise GscError(0, "invalid_property")
        return "https://www.googleapis.com/webmasters/v3/sites/%s/searchAnalytics/query" % quote(property, safe="")

    def _rows(self, property, start, end, dimensions):
        url = self._url(property)
        results, seen = [], set()
        for page in range(self.max_pages):
            body = {"startDate": start, "endDate": end, "dimensions": ["date"] + dimensions,
                    "type": "web", "dataState": "final", "rowLimit": ROW_LIMIT, "startRow": page * ROW_LIMIT}
            answer = self._request(url, headers={"Authorization": "Bearer " + self._token()}, body=body)
            rows = answer.get("rows", [])
            if not isinstance(rows, list) or len(rows) > ROW_LIMIT:
                raise GscError(200, "invalid_rows")
            for row in rows:
                if not isinstance(row, dict):
                    raise GscError(200, "invalid_row")
                keys = row.get("keys")
                if (not isinstance(keys, list) or len(keys) != len(dimensions) + 1
                        or any(not isinstance(k, str) or not k or "\x00" in k for k in keys)):
                    raise GscError(200, "invalid_keys")
                row_day = iso_day(keys[0])
                if not start <= row_day <= end:
                    raise GscError(200, "unexpected_date")
                identity = tuple(keys)
                if identity in seen:
                    raise GscError(200, "duplicate_row")
                seen.add(identity)
                values = {}
                for metric in ("clicks", "impressions", "position"):
                    value = row.get(metric)
                    if (not finite_number(value) or value < 0
                            or (metric != "position" and int(value) != value)):
                        raise GscError(200, "invalid_metrics")
                    values[metric] = float(value) if metric == "position" else int(value)
                values["day"] = row_day
                for dimension, value in zip(dimensions, keys[1:]):
                    if dimension == "page":
                        try:
                            parsed = urlsplit(value)
                            valid = (parsed.scheme in ("https", "http") and parsed.netloc
                                     and not parsed.username and not parsed.password
                                     and not any(c.isspace() or ord(c) < 32 for c in value))
                        except ValueError:
                            valid = False
                        if not valid:
                            raise GscError(200, "invalid_page")
                    if dimension == "country" and not re.fullmatch("[A-Za-z]{3}", value):
                        raise GscError(200, "invalid_country")
                    if dimension == "device" and value.lower() not in ("desktop", "mobile", "tablet"):
                        raise GscError(200, "invalid_device")
                    values["url" if dimension == "page" else dimension] = value
                results.append(values)
            if len(rows) < ROW_LIMIT:
                return results
        raise GscError(200, "pagination_limit")

    def fetch(self, property, day, dataset):
        day = iso_day(day)
        if dataset not in DIMENSIONS:
            raise GscError(0, "invalid_dataset")
        return [{k: v for k, v in row.items() if k != "day"}
                for row in self._rows(property, day, day, DIMENSIONS[dataset])]

    def first_incomplete(self, property, start, end):
        """The first day Google may still change; every earlier day is final, rows or not.

        Google names it only for fresh data grouped by date, and only when the range has rows:
        a property without impressions answers without it, and so does this — None.
        """
        start, end = iso_day(start), iso_day(end)
        if start > end:
            raise GscError(0, "invalid_date_range")
        body = {"startDate": start, "endDate": end, "dimensions": ["date"], "type": "web", "dataState": "all"}
        answer = self._request(self._url(property), headers={"Authorization": "Bearer " + self._token()}, body=body)
        metadata = answer.get("metadata")
        if metadata is None:
            return None
        if not isinstance(metadata, dict):
            raise GscError(200, "invalid_metadata")
        named = metadata.get("firstIncompleteDate")
        if named is None:
            return None
        try:
            boundary = date.fromisoformat(iso_day(named))
        except GscError:
            raise GscError(200, "invalid_metadata") from None
        # A date outside the asked range would certify fresh days as final, or none at all.
        if not date.fromisoformat(start) <= boundary <= date.fromisoformat(end) + timedelta(days=1):
            raise GscError(200, "invalid_metadata")
        return boundary

    def finalized_days(self, property, start, end):
        start, end = iso_day(start), iso_day(end)
        if start > end:
            raise GscError(0, "invalid_date_range")
        return {row["day"] for row in self._rows(property, start, end, [])}
