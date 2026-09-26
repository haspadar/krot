# -*- coding: utf-8 -*-
# MIT License
"""HTTP for the site-launch modules.

One rule runs through every module that uses this: "could not ask" is not "no".
A timeout, a dropped connection, a 5xx or an answer that is not JSON raises
Unreachable, and a module that catches it must stop — never read it as "the zone
does not exist" and go on to create a second one. busel/tsbelgie is what that
reading costs: a launch that looked at a failed answer, decided nothing was
there, and wrote.

4xx answers are returned, not raised: what a 400 means differs per API (Search
Console's 400 is "not visible yet", Bing's is "try in a minute", Cloudflare's is
a refusal), and only the module knows which it is looking at.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import time

from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError
from ansible.module_utils.six.moves.urllib.parse import urlencode
from ansible.module_utils.urls import open_url


class Unreachable(Exception):
    """The question could not be asked, so there is no answer to act on."""


class Http:
    """JSON over HTTP with retries for the failures that pass by themselves."""

    # Retried: the network, the server's own trouble, and rate limiting. Not
    # retried: every other 4xx — asking again gets the same refusal.
    RETRIED = (429, 500, 502, 503, 504)

    def __init__(self, base, headers=None, timeout=30, attempts=3, pause=2.0):
        self.base = base.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.attempts = attempts
        self.pause = pause

    def call(self, method, path, query=None, body=None):
        """Returns (status, decoded JSON or None for an empty body)."""
        url = self.base + path
        if query:
            url += "?" + urlencode(query)
        headers = dict(self.headers)
        data = None
        if body is not None:
            data = json.dumps(body)
            headers["Content-Type"] = "application/json"

        reason = "no attempt was made"
        for attempt in range(self.attempts):
            if attempt:
                time.sleep(self.pause)
            try:
                response = open_url(url, method=method, data=data, headers=headers,
                                    timeout=self.timeout, validate_certs=True)
                status, raw = response.getcode(), response.read()
            except HTTPError as error:
                status, raw = error.code, error.read()
            except (URLError, OSError) as error:
                reason = "%s %s: %s" % (method, url_without_secrets(url), error)
                continue
            if status in self.RETRIED:
                reason = "%s %s answered %d" % (method, url_without_secrets(url), status)
                continue
            return status, decoded(raw, method, url)
        raise Unreachable(reason)


def decoded(raw, method, url):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        # A captive portal, a proxy's error page, a tunnel that answered for the
        # service: all of them 200 with HTML. Not an answer from the API.
        raise Unreachable("%s %s answered with something that is not JSON" % (method, url_without_secrets(url)))


def url_without_secrets(url):
    # Bing takes its key in the query string, and error messages end up in the
    # play's output. The path is enough to tell which call failed.
    return url.split("?", 1)[0]


def wait(ask, ready, attempts, delay):
    """Asks until the answer is ready; returns the last answer either way.

    For the "not yet" that every one of these services has — Bing's empty
    verification code, Yandex's uin, a verification the resolver has not seen.
    The caller decides what an answer that never became ready means.
    """
    answer = ask()
    for _ in range(attempts - 1):
        if ready(answer):
            return answer
        time.sleep(delay)
        answer = ask()
    return answer
