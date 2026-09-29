# -*- coding: utf-8 -*-
# MIT License
"""Google's APIs as the site-launch modules need them: a service account's
token, and one place that reads Google's refusals.

Google has no plain API key for Search Console or the Analytics Admin API.
Every call carries a bearer token, and a service account earns one by signing a
claim with its private key and trading the signature for the token. The same
account serves both products, each under its own scope, so tokens are asked for
per scope and kept for the rest of the module's run.

The signing itself lives in google_jwt.py, which krot-index shares on the
machine; what stays here is the part that goes over Ansible's HTTP client.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.google_jwt import (  # noqa: F401
    CRYPTOGRAPHY_ERROR,
    HAS_CRYPTOGRAPHY,
    TOKEN_URI,
    ServiceAccountKey,
    encoded,
    reason,
)

# Shared by every Google module, so the key and the token address are spelled
# the same way in all of them.
ARGUMENTS = dict(
    service_account=dict(type="str", required=True, no_log=True),
    token_uri=dict(type="str", default=TOKEN_URI),
)


class Refused(Exception):
    """Google answered and said no. `status` tells a delay from a dead end."""

    def __init__(self, method, path, status, answer):
        self.status = status
        super(Refused, self).__init__("Google refused %s %s (HTTP %d): %s" % (method, path, status, reason(answer)))


def call(http, method, path, query=None, body=None):
    """Returns the decoded answer of a call Google accepted, or raises Refused."""
    status, answer = http.call(method, path, query, body)
    if status >= 400:
        raise Refused(method, path, status, answer)
    return answer


class ServiceAccount:
    def __init__(self, key_json, token_uri=TOKEN_URI):
        self.key = ServiceAccountKey(key_json)
        self.email = self.key.email
        self.token_uri = token_uri
        self.tokens = {}

    def http(self, base, scope):
        return Http(base, headers={"Authorization": "Bearer " + self.token(scope)})

    def token(self, scope):
        if scope not in self.tokens:
            self.tokens[scope] = self.exchange(scope)
        return self.tokens[scope]

    def exchange(self, scope):
        status, answer = Http(self.token_uri).call("POST", "", form=self.key.grant(scope, self.token_uri))
        if status >= 400:
            raise Refused("POST", self.token_uri, status, answer)
        access = answer.get("access_token") if isinstance(answer, dict) else None
        if not access:
            raise Unreachable("Google's token endpoint answered without an access token")
        return access
