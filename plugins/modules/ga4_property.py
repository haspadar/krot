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
  - Looks the property up by display name (the domain) across every page of
    the account's properties, and creates it only when none is found.
  - A property without a web stream — a launch interrupted between the two
    calls — gets its stream rather than a second property.
  - The time zone and currency of an existing property are brought to the
    given values. The time zone decides where a day begins; a German site
    counted in Europe/Minsk has its days cut an hour off.
  - The service account needs the Administrator role on the account, not on a
    property. Without it the API answers 403 in a way that reads like a
    missing property.
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
  time_zone:
    description: IANA time zone the property counts days in, from the site's country.
    type: str
    required: true
  currency_code:
    description: ISO 4217 currency the property reports revenue in.
    type: str
    required: true
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
    time_zone: Europe/Berlin
    currency_code: EUR
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
drift:
  description:
    - Each field of an existing property that differs, with what it holds and
      what it gets. A new time zone moves where every past day of the reports
      begins, so a dry run names it rather than only saying "changed".
  type: dict
  returned: always
  sample: {timeZone: {from: Europe/Minsk, to: Europe/Berlin}}
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

API_URL = "https://analyticsadmin.googleapis.com/v1beta"
SCOPE = "https://www.googleapis.com/auth/analytics.edit"


class Admin:
    def __init__(self, http, account):
        self.http = http
        self.account = account

    def find(self, domain):
        """The property named after the domain, or None."""
        query = dict(filter="parent:accounts/" + self.account, pageSize=200)
        while True:
            answer = call(self.http, "GET", "/properties", query=query)
            if not isinstance(answer, dict):
                raise Unreachable("Analytics answered the property list without a body")
            # An account with no properties answers {} — a real "none".
            properties = answer.get("properties", [])
            if not isinstance(properties, list):
                raise Unreachable("Analytics answered the property list without a list")
            for found in properties:
                if isinstance(found, dict) and found.get("displayName") == domain and number(found):
                    return found
            # Every page, not the first: a property past the cut would read as
            # absent and be created a second time.
            page = answer.get("nextPageToken")
            if not page:
                return None
            query = dict(query, pageToken=page)

    def measurement(self, property_id):
        """The web stream's measurement id, or None when the property has none."""
        query = dict(pageSize=200)
        while True:
            answer = call(self.http, "GET", "/properties/%s/dataStreams" % property_id, query=query)
            if not isinstance(answer, dict):
                raise Unreachable("Analytics answered the stream list without a body")
            streams = answer.get("dataStreams", [])
            if not isinstance(streams, list):
                raise Unreachable("Analytics answered the stream list without a list")
            for stream in streams:
                web = stream.get("webStreamData") if isinstance(stream, dict) else None
                if isinstance(web, dict) and web.get("measurementId"):
                    return web["measurementId"]
            # Every page, as with properties: "no web stream" is what triggers
            # creating one, and a web stream behind app streams on a later page
            # would be answered with a second one — two measurement ids, the
            # site's traffic split between them.
            page = answer.get("nextPageToken")
            if not page:
                return None
            query = dict(query, pageToken=page)

    def add_stream(self, property_id, domain):
        call(self.http, "POST", "/properties/%s/dataStreams" % property_id, body=dict(
            type="WEB_DATA_STREAM", displayName=domain, webStreamData=dict(defaultUri="https://" + domain)))


def number(found):
    """The numeric id inside a property's resource name (properties/550407450)."""
    name = found.get("name") or ""
    return name[len("properties/"):] if name.startswith("properties/") else ""


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            account_id=dict(type="str", required=True),
            time_zone=dict(type="str", required=True),
            currency_code=dict(type="str", required=True),
            api_url=dict(type="str", default=API_URL),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    if not HAS_CRYPTOGRAPHY:
        module.fail_json(msg=missing_required_lib("cryptography"), exception=CRYPTOGRAPHY_ERROR)
    p = module.params
    domain = p["domain"]
    wanted = dict(timeZone=p["time_zone"], currencyCode=p["currency_code"])
    changed = False

    try:
        account = ServiceAccount(p["service_account"], p["token_uri"])
    except ValueError as error:
        module.fail_json(msg=str(error))

    try:
        admin = Admin(account.http(p["api_url"], SCOPE), p["account_id"])
        found = admin.find(domain)

        if found is None:
            if module.check_mode:
                module.exit_json(changed=True, property_id="", measurement_id="", drift={})
            call(admin.http, "POST", "/properties", body=dict(
                parent="accounts/" + p["account_id"], displayName=domain, **wanted))
            changed = True
            found = admin.find(domain)
            if found is None:
                module.fail_json(msg="Analytics accepted property %s but does not list it" % domain, changed=changed)

        property_id = number(found)
        drift = sorted(field for field, value in wanted.items() if found.get(field) != value)
        moves = dict((field, {"from": found.get(field), "to": wanted[field]}) for field in drift)
        if drift:
            if module.check_mode:
                module.exit_json(changed=True, property_id=property_id,
                                 measurement_id=admin.measurement(property_id) or "", drift=moves)
            call(admin.http, "PATCH", "/properties/%s" % property_id,
                 query=dict(updateMask=",".join(drift)), body=dict((field, wanted[field]) for field in drift))
            changed = True

        measurement = admin.measurement(property_id)
        if measurement is None:
            # Half-created: the property exists, its stream does not. Finishing
            # it here is what lets a rerun heal an interrupted launch.
            if module.check_mode:
                module.exit_json(changed=True, property_id=property_id, measurement_id="", drift=moves)
            admin.add_stream(property_id, domain)
            changed = True
            measurement = admin.measurement(property_id)
            if measurement is None:
                module.fail_json(msg="Analytics accepted the stream of %s but lists none" % domain,
                                 changed=changed, property_id=property_id)

        if drift:
            again = admin.find(domain) or {}
            kept = [field for field in drift if again.get(field) != wanted[field]]
            if kept:
                module.fail_json(msg="Analytics accepted but did not keep: %s" % ", ".join(kept),
                                 changed=changed, property_id=property_id, measurement_id=measurement)

        module.exit_json(changed=changed, property_id=property_id, measurement_id=measurement, drift=moves)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=changed)


if __name__ == "__main__":
    main()
