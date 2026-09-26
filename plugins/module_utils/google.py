# -*- coding: utf-8 -*-
# MIT License
"""Google's APIs as the site-launch modules need them: a service account's
token, and one place that reads Google's refusals.

Google has no plain API key for Search Console or the Analytics Admin API.
Every call carries a bearer token, and a service account earns one by signing a
claim with its private key and trading the signature for the token. The same
account serves both products, each under its own scope, so tokens are asked for
per scope and kept for the rest of the module's run.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import json
import time
import traceback


from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    HAS_CRYPTOGRAPHY = True
    CRYPTOGRAPHY_ERROR = None
except ImportError:
    HAS_CRYPTOGRAPHY = False
    CRYPTOGRAPHY_ERROR = traceback.format_exc()

TOKEN_URI = "https://oauth2.googleapis.com/token"

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


def reason(answer):
    # Two shapes: the APIs say {"error": {"message": ...}}, the token endpoint
    # says {"error": "invalid_grant", "error_description": ...}. Both are kept,
    # since a missing role and a revoked key otherwise look alike from outside.
    if not isinstance(answer, dict):
        return "no reason given"
    error = answer.get("error")
    if isinstance(error, dict):
        return error.get("message") or error.get("status") or "no reason given"
    if isinstance(error, str):
        return "%s: %s" % (error, answer.get("error_description") or "no description")
    return "no reason given"


def call(http, method, path, query=None, body=None):
    """Returns the decoded answer of a call Google accepted, or raises Refused."""
    status, answer = http.call(method, path, query, body)
    if status >= 400:
        raise Refused(method, path, status, answer)
    return answer


class ServiceAccount:
    def __init__(self, key_json, token_uri=TOKEN_URI):
        try:
            key = json.loads(key_json)
        except ValueError:
            key = None
        # The message never quotes the key: a malformed one is still mostly a
        # private key, and error messages end up in the play's output.
        if not isinstance(key, dict) or not key.get("client_email") or not key.get("private_key"):
            raise ValueError("the Google key is not a service account key file")
        self.email = key["client_email"]
        self.private_key = key["private_key"]
        self.token_uri = token_uri
        self.tokens = {}

    def http(self, base, scope):
        return Http(base, headers={"Authorization": "Bearer " + self.token(scope)})

    def token(self, scope):
        if scope not in self.tokens:
            self.tokens[scope] = self.exchange(scope)
        return self.tokens[scope]

    def exchange(self, scope):
        now = int(time.time())
        assertion = self.sign(dict(iss=self.email, scope=scope, aud=self.token_uri, iat=now, exp=now + 3600))
        form = dict(grant_type="urn:ietf:params:oauth:grant-type:jwt-bearer", assertion=assertion)
        status, answer = Http(self.token_uri).call("POST", "", form=form)
        if status >= 400:
            raise Refused("POST", self.token_uri, status, answer)
        access = answer.get("access_token") if isinstance(answer, dict) else None
        if not access:
            raise Unreachable("Google's token endpoint answered without an access token")
        return access

    def sign(self, claim):
        header = encoded(json.dumps(dict(alg="RS256", typ="JWT")).encode())
        body = encoded(json.dumps(claim).encode())
        signing = header + b"." + body
        key = serialization.load_pem_private_key(self.private_key.encode(), password=None)
        signature = key.sign(signing, padding.PKCS1v15(), hashes.SHA256())
        return (signing + b"." + encoded(signature)).decode()


def encoded(raw):
    """URL-safe base64 without padding, as JWT wants it."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=")
