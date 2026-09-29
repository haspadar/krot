"""The one way this program reaches the network.

urllib rather than anything installed: the machine has Python and the packages
Ubuntu ships, and a pip dependency would be a second way for a night to fail.
"""

import http.client
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


# The sitemap protocol's own ceiling for one file, uncompressed. A body larger
# than this is not a sitemap, and reading it whole would put the night's memory
# in the hands of whatever answered.
MAX_BYTES = 50 * 1024 * 1024


class Unreachable(Exception):
    """Nobody answered: DNS, a refused connection, a timeout. Not the same as a "no"."""


class _NoRedirects(HTTPRedirectHandler):
    # A sitemap that redirects is not the address the engines were handed, and a
    # redirect followed quietly reads a login page as the site. Refused here, it
    # surfaces as its own status and the caller decides.
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = build_opener(_NoRedirects)


def call(method, url, headers=None, body=None, form=None, timeout=60):
    """Sends one request and returns (status, raw body). Raises Unreachable only.

    A refusal is an answer, so 4xx and 5xx come back as statuses rather than as
    exceptions: every engine reads its refusals differently, and one that had to
    catch them first would be tempted to read them all alike.
    """
    # Only the web: a sitemap index names the next address itself, and one
    # naming file:///etc/… or ftp:// would otherwise be opened by this program.
    if urlsplit(url).scheme not in ("http", "https"):
        raise Unreachable("%s %s: only http and https are fetched" % (method, url))
    headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urlencode(form).encode()
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    headers.setdefault("User-Agent", "krot-index")
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as answer:
            return answer.status, _bounded(answer, method, url)
    except HTTPError as refusal:
        return refusal.code, _bounded(refusal, method, url)
    except (URLError, socket.timeout, OSError, http.client.HTTPException, ValueError) as failure:
        # HTTPException: a body cut off midway, a status line that is not one.
        # ValueError: an address urllib cannot even parse. Both are "nobody
        # answered usefully", and escaping as themselves they would end the walk
        # over every site instead of this one request.
        raise Unreachable("%s %s: %s" % (method, url, str(failure) or type(failure).__name__))


def _bounded(answer, method, url):
    raw = answer.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Unreachable("%s %s: answered more than %d bytes" % (method, url, MAX_BYTES))
    return raw


def decoded(raw):
    """The JSON in a body, or None where it is not JSON — an HTML error page, an empty 5xx."""
    try:
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except (ValueError, UnicodeDecodeError):
        return None
