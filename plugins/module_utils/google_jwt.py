# -*- coding: utf-8 -*-
# MIT License
"""A Google service account's signed claim, and nothing that needs Ansible.

Kept apart from google.py because two programs sign with the same key: the
site-launch modules, which run under Ansible, and krot-index, which runs on the
machine from a timer where Ansible is not installed. google.py reaches the
network through ansible.module_utils.urls; this file reaches nothing, so both
can import it — the modules as module_utils, krot-index through a symlink in its
own package. One copy of the signing, because two would drift the first time
Google changed what it wants in a claim.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import json
import time
import traceback

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    HAS_CRYPTOGRAPHY = True
    CRYPTOGRAPHY_ERROR = None
except ImportError:
    HAS_CRYPTOGRAPHY = False
    CRYPTOGRAPHY_ERROR = traceback.format_exc()

TOKEN_URI = "https://oauth2.googleapis.com/token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"


class ServiceAccountKey:
    """The key file Google issues, read once and able to sign a claim for a scope."""

    def __init__(self, key_json):
        try:
            key = json.loads(key_json)
        except ValueError:
            key = None
        # The message never quotes the key: a malformed one is still mostly a
        # private key, and error messages end up in the play's output and the
        # journal.
        if not isinstance(key, dict) or not key.get("client_email") or not key.get("private_key"):
            raise ValueError("the Google key is not a service account key file")
        self.email = key["client_email"]
        self.private_key = key["private_key"]

    def assertion(self, scope, token_uri, now=None):
        """The signed claim a token endpoint trades for a bearer token, valid for an hour."""
        issued = int(time.time()) if now is None else now
        return self.sign(dict(iss=self.email, scope=scope, aud=token_uri, iat=issued, exp=issued + 3600))

    def grant(self, scope, token_uri):
        """The form a token endpoint takes, ready to post."""
        return dict(grant_type=GRANT_TYPE, assertion=self.assertion(scope, token_uri))

    def sign(self, claim):
        header = encoded(json.dumps(dict(alg="RS256", typ="JWT")).encode())
        body = encoded(json.dumps(claim).encode())
        signing = header + b"." + body
        key = serialization.load_pem_private_key(self.private_key.encode(), password=None)
        signature = key.sign(signing, padding.PKCS1v15(), hashes.SHA256())
        return (signing + b"." + encoded(signature)).decode()


def reason(answer):
    """Google's own words for a refusal, from either shape it answers in.

    Two shapes: the APIs say {"error": {"message": ...}}, the token endpoint says
    {"error": "invalid_grant", "error_description": ...}. Both are kept, since a
    missing role and a revoked key otherwise look alike from outside.
    """
    if not isinstance(answer, dict):
        return "no reason given"
    error = answer.get("error")
    if isinstance(error, dict):
        return error.get("message") or error.get("status") or "no reason given"
    if isinstance(error, str):
        return "%s: %s" % (error, answer.get("error_description") or "no description")
    return "no reason given"


def encoded(raw):
    """URL-safe base64 without padding, as JWT wants it."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=")
