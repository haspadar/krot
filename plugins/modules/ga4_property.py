#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: ga4_property
short_description: Finds or creates a GA4 property with a web stream for a domain
description:
  - Looks across every page for the domain name or a matching web stream URL,
    and creates a property only when no match exists.
  - A property without a web stream — a launch interrupted between the two
    calls — gets its stream rather than a second property.
  - Requires the explicit human owner to own the GSC domain and administer the Analytics account.
  - Existing property settings are never patched. New properties use Europe/Berlin and EUR.
  - Reuses the unique matching domain URL stream; explicit IDs resolve ambiguity.
  - Needs the cryptography library on the machine running the module.
  - In check mode nothing is written.
options:
  domain:
    description: The site's domain; it is the property's display name and the stream's address.
    type: str
    required: true
  account_id:
    description: Numeric id of the Analytics account the property belongs to.
    type: str
    required: true
  owner_email:
    description: Human GSC owner who must already administer this Analytics account.
    type: str
    required: true
  property_id:
    description: Explicit existing numeric property ID, never silently replaced.
    type: str
    default: ""
  stream_id:
    description: Explicit existing numeric stream ID, requires property_id and matching domain URL.
    type: str
    default: ""
  access_api_url:
    description: Analytics access bindings API endpoint, changed only by tests.
    type: str
    default: https://analyticsadmin.googleapis.com/v1alpha
  google_api_url:
    description: Site Verification API endpoint, changed only by tests.
    type: str
    default: https://www.googleapis.com
  service_account:
    description: The service account's key file, as JSON text.
    type: str
    required: true
  token_uri:
    description: Google's token address; changed only by tests.
    type: str
    default: https://oauth2.googleapis.com/token
  api_url:
    description: Analytics Admin API address; changed only by tests.
    type: str
    default: https://analyticsadmin.googleapis.com/v1beta
requirements:
  - cryptography
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Find or create the property
  haspadar.krot.ga4_property:
    domain: example.de
    account_id: "{{ ga4_account_id }}"
    owner_email: "{{ human_gsc_owner }}"
    service_account: "{{ google_key }}"
  delegate_to: localhost
  register: ga4
"""

RETURN = r"""
property_id:
  description: Numeric id of the property. Empty in check mode when it would be created.
  type: str
  returned: always
measurement_id:
  description: The web stream's measurement id (C(G-...)). Empty in check mode when it would be created.
  type: str
  returned: always
stream_id:
  description: Numeric web stream ID, empty when check mode would create it.
  type: str
  returned: always
time_zone:
  description: Existing property time zone or Europe/Berlin for a planned new property.
  type: str
  returned: always
account_id:
  description: Explicit Analytics account ID.
  type: str
  returned: always
owner_email:
  description: Explicit human owner.
  type: str
  returned: always
owner_verified:
  description: Whether GSC ownership was verified; false for an unverified new domain in check mode.
  type: bool
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule, missing_required_lib

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.google import (
    ARGUMENTS,
    CRYPTOGRAPHY_ERROR,
    HAS_CRYPTOGRAPHY,
    Refused,
    ServiceAccount,
    call,
)

import re
from urllib.parse import quote, urlsplit

USERS_SCOPE = "https://www.googleapis.com/auth/analytics.manage.users"
VERIFY_SCOPE = "https://www.googleapis.com/auth/siteverification"

API_URL = "https://analyticsadmin.googleapis.com/v1beta"
SCOPE = "https://www.googleapis.com/auth/analytics.edit"


def pages(http, path, key, query=None):
    query = dict(query or {}, pageSize=200)
    result, seen = [], set()
    while True:
        answer = call(http, "GET", path, query=query)
        if not isinstance(answer, dict) or not isinstance(answer.get(key, []), list):
            raise Unreachable("Analytics answered %s without a valid %s list" % (path, key))
        rows = answer.get(key, [])
        if any(not isinstance(row, dict) for row in rows):
            raise Unreachable("Analytics answered %s with a malformed record" % path)
        result.extend(rows)
        page = answer.get("nextPageToken")
        if not page:
            return result
        if not isinstance(page, str) or page in seen:
            raise Unreachable("Analytics repeated or malformed a pagination token")
        seen.add(page)
        query["pageToken"] = page


def numeric(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]+", value) is not None


def number(found):
    name = found.get("name", "")
    value = name.removeprefix("properties/") if isinstance(name, str) else ""
    if not numeric(value):
        raise Unreachable("Analytics returned a malformed property resource name")
    return value


def matching(stream, domain, property_id):
    name = stream.get("name", "")
    prefix = "properties/%s/dataStreams/" % property_id
    web = stream.get("webStreamData")
    if stream.get("type") != "WEB_DATA_STREAM":
        return False
    if not isinstance(web, dict) or not isinstance(name, str) or not name.startswith(prefix) or not numeric(name[len(prefix):]):
        raise Unreachable("Analytics returned a malformed web stream")
    uri = web.get("defaultUri", "")
    if not isinstance(uri, str):
        raise Unreachable("Analytics returned a malformed stream URI")
    url = urlsplit(uri)
    return url.scheme in ("http", "https") and url.hostname in (domain, "www." + domain)


def proof(account, p, check):
    owner = p["owner_email"].strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", owner) or owner.endswith(".gserviceaccount.com"):
        raise ValueError("owner_email must explicitly name a human Google account")
    # Account membership is checked first, even for a new domain in check mode.
    bindings = pages(account.http(p["access_api_url"], USERS_SCOPE),
                     "/accounts/%s/accessBindings" % p["account_id"], "accessBindings")
    if not any(str(b.get("user", "")).lower() == owner and isinstance(b.get("roles"), list)
               and "predefinedRoles/admin" in b["roles"] for b in bindings):
        raise ValueError("Human GSC owner %s is not an administrator of explicit Analytics account %s" %
                         (owner, p["account_id"]))
    resource = "/siteVerification/v1/webResource/" + quote("dns://" + p["domain"], safe="")
    try:
        answer = call(account.http(p["google_api_url"], VERIFY_SCOPE), "GET", resource)
    except Refused as error:
        if check and error.status in (403, 404) and "not an owner" in str(error).lower():
            return False
        raise
    owners = answer.get("owners") if isinstance(answer, dict) else None
    if not isinstance(owners, list) or not owners:
        raise Unreachable("Google answered the GSC owners without a nonempty list")
    if owner not in [str(email).lower() for email in owners]:
        raise ValueError("Human Analytics account administrator %s is not a GSC owner of %s" % (owner, p["domain"]))
    return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            account_id=dict(type="str", required=True),
            owner_email=dict(type="str", required=True),
            property_id=dict(type="str", default=""),
            stream_id=dict(type="str", default=""),
            api_url=dict(type="str", default=API_URL),
            access_api_url=dict(type="str", default="https://analyticsadmin.googleapis.com/v1alpha"),
            google_api_url=dict(type="str", default="https://www.googleapis.com"),
            **ARGUMENTS
        ), supports_check_mode=True)
    if not HAS_CRYPTOGRAPHY:
        module.fail_json(msg=missing_required_lib("cryptography"), exception=CRYPTOGRAPHY_ERROR)
    p, changed = module.params, False
    result = dict(property_id="", stream_id="", measurement_id="", time_zone="Europe/Berlin",
                  account_id=p["account_id"], owner_email=p["owner_email"].strip().lower(), owner_verified=False)
    try:
        if not numeric(p["account_id"]) or any(p[k] and not numeric(p[k]) for k in ("property_id", "stream_id")):
            raise ValueError("account_id, property_id and stream_id must be numeric IDs")
        if p["stream_id"] and not p["property_id"]:
            raise ValueError("stream_id requires property_id")
        labels = p["domain"].split(".")
        if (p["domain"].startswith("www.") or len(p["domain"]) > 253 or len(labels) < 2
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
                or not re.fullmatch(r"(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})", labels[-1])):
            raise ValueError("domain must be a lower-case DNS domain without a URL or www prefix")
        account = ServiceAccount(p["service_account"], p["token_uri"])
        result["owner_verified"] = proof(account, p, module.check_mode)
        http = account.http(p["api_url"], SCOPE)
        properties = pages(http, "/properties", "properties", dict(filter="parent:accounts/" + p["account_id"]))
        candidates = []
        for prop in properties:
            pid = number(prop)
            if prop.get("parent") != "accounts/" + p["account_id"]:
                raise Unreachable("Analytics returned a property from another account")
            if p["property_id"] and pid != p["property_id"]:
                continue
            streams = pages(http, "/properties/%s/dataStreams" % pid, "dataStreams")
            matches = [stream for stream in streams if matching(stream, p["domain"], pid)]
            if p["property_id"] or prop.get("displayName") == p["domain"] or matches:
                candidates.append((prop, matches))
        if len(candidates) > 1:
            raise ValueError("Ambiguous GA4 properties for %s; pass property_id explicitly" % p["domain"])
        if not candidates:
            if p["property_id"]:
                raise ValueError("Explicit property_id is not visible in the requested Analytics account")
            if module.check_mode:
                module.exit_json(changed=True, **result)
            call(http, "POST", "/properties", body=dict(parent="accounts/" + p["account_id"],
                 displayName=p["domain"], timeZone="Europe/Berlin", currencyCode="EUR"))
            changed = True
            # Read back; a lost response is never retried by the HTTP helper.
            properties = pages(http, "/properties", "properties", dict(filter="parent:accounts/" + p["account_id"]))
            found = [v for v in properties if v.get("displayName") == p["domain"]
                     and v.get("parent") == "accounts/" + p["account_id"]]
            if len(found) != 1:
                raise Unreachable("Analytics accepted the property but does not list exactly one match")
            prop = found[0]
            pid = number(prop)
            matches = [v for v in pages(http, "/properties/%s/dataStreams" % pid, "dataStreams")
                       if matching(v, p["domain"], pid)]
        else:
            prop, matches = candidates[0]
        pid = number(prop)
        result.update(property_id=pid, time_zone=prop.get("timeZone", ""))
        if p["stream_id"]:
            matches = [v for v in matches if v["name"].endswith("/" + p["stream_id"])]
            if not matches:
                raise ValueError("Explicit stream_id is missing or its URL does not match this domain")
        if len(matches) > 1:
            raise ValueError("Ambiguous GA4 web streams for %s; pass stream_id explicitly" % p["domain"])
        if not matches:
            if module.check_mode:
                module.exit_json(changed=True, **result)
            call(http, "POST", "/properties/%s/dataStreams" % pid, body=dict(type="WEB_DATA_STREAM",
                 displayName=p["domain"], webStreamData=dict(defaultUri="https://" + p["domain"])))
            changed = True
            matches = [v for v in pages(http, "/properties/%s/dataStreams" % pid, "dataStreams")
                       if matching(v, p["domain"], pid)]
            if len(matches) != 1:
                raise Unreachable("Analytics accepted the web stream but does not list exactly one match")
        stream = matches[0]
        measurement = stream["webStreamData"].get("measurementId", "")
        if not isinstance(measurement, str) or not re.fullmatch(r"G-[A-Z0-9]+", measurement):
            raise Unreachable("Analytics returned the web stream without a valid measurement ID")
        result.update(stream_id=stream["name"].rsplit("/", 1)[1], measurement_id=measurement)
        module.exit_json(changed=changed or not result["owner_verified"], **result)
    except (ValueError, Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=changed, **result)


if __name__ == "__main__":
    main()
