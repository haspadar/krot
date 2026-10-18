#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: ga4_access
short_description: Lets the key that collects traffic read a GA4 property, and proves it
description:
  - Reads the property with the collecting key (Data API C(runReport)). When that answers,
    nothing is written — this also covers a collecting key that is the launching key, and
    access the key inherits from the account.
  - When the collecting key is refused for lack of rights on the property, the launching
    key grants it the Viewer role on that one property (Admin API C(accessBindings)) and the
    property is read again, until the grant shows or the attempts run out. A grant takes a
    few seconds to reach the Data API.
  - Fails, rather than leaving a 403 for the collector's next night, when the launching key
    cannot grant (it is not an administrator of the property) or the grant does not show.
    The message names the collecting key's address and the manual step.
  - Grants only on Google's own words for missing rights on the property. Any other refusal
    (the Data API switched off in the collecting key's project, a restricted key, a quota)
    fails as it is, with Google's reason, and nothing is written — no role fixes those.
  - A collecting key that is the launching key is never granted anything; it is only waited for.
  - Only the Viewer role, only on the given property. Existing bindings are never changed or removed.
  - Needs the cryptography library on the machine running the module.
  - In check mode nothing is written; C(changed) says whether a grant is due.
options:
  property_id:
    description: Numeric id of the GA4 property (from M(haspadar.krot.ga4_property)).
    type: str
    required: true
  service_account:
    description: The launching key, as JSON text. The one that created the property.
    type: str
    required: true
  reader_service_account:
    description: The key that collects traffic, as JSON text. The key this module makes sure can read.
    type: str
    required: true
  token_uri:
    description: Google's token address; changed only by tests.
    type: str
    default: https://oauth2.googleapis.com/token
  api_url:
    description: Analytics Admin API address, the v1alpha one because access bindings exist only there; changed only by tests.
    type: str
    default: https://analyticsadmin.googleapis.com/v1alpha
  data_api_url:
    description: Analytics Data API address; changed only by tests.
    type: str
    default: https://analyticsdata.googleapis.com/v1beta
  wait_attempts:
    description: How many times the property is read after a grant before giving up.
    type: int
    default: 8
  wait_delay:
    description: Seconds between those reads.
    type: int
    default: 4
requirements:
  - cryptography
author:
  - haspadar
"""

EXAMPLES = r"""
- name: The collecting key reads the new property
  haspadar.krot.ga4_access:
    property_id: "{{ ga4.property_id }}"
    service_account: "{{ launch_key }}"
    reader_service_account: "{{ collecting_key }}"
  delegate_to: localhost
"""

RETURN = r"""
reader:
  description: The collecting key's address, the one the property is readable by.
  type: str
  returned: always
granted:
  description: Whether this run gave the collecting key the Viewer role.
  type: bool
  returned: always
"""

import time

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

ADMIN_URL = "https://analyticsadmin.googleapis.com/v1alpha"
DATA_URL = "https://analyticsdata.googleapis.com/v1beta"
# Who may add a user to a property, and nothing wider than that.
ADMIN_SCOPE = "https://www.googleapis.com/auth/analytics.manage.users"
READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
VIEWER = "predefinedRoles/viewer"

# The smallest report there is: one metric, one day. It asks Google whether the
# key may read the property, which is all the collector's first call asks too.
PROBE = dict(dateRanges=[dict(startDate="yesterday", endDate="yesterday")], metrics=[dict(name="sessions")])


class Denied(Exception):
    """The collecting key is refused on this property."""


class IncompleteReport(Unreachable):
    """The Data API accepted the read before the requested report was ready."""


def reads(data, property_id):
    """True when the collecting key reads the property; Denied when it is refused for want of rights.

    Any other refusal (404 for a property that is not there, 400, 429) is not
    a missing right, and granting one would not cure it: it propagates.
    """
    try:
        answer = call(data, "POST", "/properties/%s:runReport" % property_id, body=PROBE)
    except Refused as error:
        if error.status != 403:
            raise
        # Only Google's own words for missing rights on the property are a reason to
        # grant. A switched-off API, a blocked key or a quota are refused with the same
        # status, and no role of the property answers them: those fail as they are, with
        # Google's reason, and nothing is written. If Google rewords this message the
        # module fails loudly and grants nothing, which is the safe side to err on.
        if "sufficient permissions" not in str(error).lower():
            raise
        raise Denied(str(error))
    # A brand-new property with no events omits metricHeaders even after Viewer has
    # propagated. Its accepted report still identifies itself and carries the property's
    # metadata — measured on two live properties on 2026-10-18. Those Google-specific fields,
    # unlike a bare {}, prove this is a report from the requested API rather than a proxy's
    # JSON page or a response from a wrong data_api_url.
    metadata = answer.get("metadata") if isinstance(answer, dict) else None
    if (isinstance(answer, dict) and "metricHeaders" not in answer
            and answer.get("kind") == "analyticsData#runReport" and isinstance(metadata, dict)
            and isinstance(metadata.get("currencyCode"), str) and isinstance(metadata.get("timeZone"), str)):
        return True
    headers = answer.get("metricHeaders") if isinstance(answer, dict) else None
    if not isinstance(headers, list) or not any(isinstance(h, dict) and h.get("name") == "sessions"
                                                for h in headers):
        raise IncompleteReport(
            "Analytics answered the report of property %s without the requested metric" % property_id)
    return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            property_id=dict(type="str", required=True),
            reader_service_account=dict(type="str", required=True, no_log=True),
            api_url=dict(type="str", default=ADMIN_URL),
            data_api_url=dict(type="str", default=DATA_URL),
            wait_attempts=dict(type="int", default=8),
            wait_delay=dict(type="int", default=4),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    if not HAS_CRYPTOGRAPHY:
        module.fail_json(msg=missing_required_lib("cryptography"), exception=CRYPTOGRAPHY_ERROR)
    p = module.params
    property_id = p["property_id"]

    try:
        launcher = ServiceAccount(p["service_account"], p["token_uri"])
        reader = ServiceAccount(p["reader_service_account"], p["token_uri"])
    except ValueError as error:
        module.fail_json(msg=str(error))

    manual = ("Give %s the Viewer role on property %s: Analytics > Admin > Property access management, "
              "or POST %s/properties/%s/accessBindings with the key of an account administrator."
              % (reader.email, property_id, p["api_url"], property_id))
    granted = False

    try:
        data = reader.http(p["data_api_url"], READ_SCOPE)
        try:
            reads(data, property_id)
            module.exit_json(changed=False, granted=False, reader=reader.email)
        except Denied as denied:
            first = str(denied)

        # The launching key reading its own property is refused only while rights reach the
        # Data API after the property is made; a role it lacks is not for it to grant itself.
        same_key = reader.email == launcher.email

        if module.check_mode:
            module.exit_json(changed=not same_key, granted=False, reader=reader.email)

        try:
            if not same_key:
                call(launcher.http(p["api_url"], ADMIN_SCOPE), "POST",
                     "/properties/%s/accessBindings" % property_id, body=dict(user=reader.email, roles=[VIEWER]))
                granted = True
        except Refused as error:
            # 409: a binding is already there, and the read above says it is not
            # in force yet — the wait below covers it, as it covers a fresh one.
            if error.status == 409:
                granted = False
            elif error.status in (401, 403):
                module.fail_json(msg="%s cannot grant access to property %s: %s. %s"
                                     % (launcher.email, property_id, error, manual))
            else:
                raise

        attempts = max(p["wait_attempts"], 1)
        for attempt in range(attempts):
            if attempt:
                time.sleep(p["wait_delay"])
            try:
                reads(data, property_id)
                module.exit_json(changed=granted, granted=granted, reader=reader.email)
            except (Denied, IncompleteReport):
                continue
        module.fail_json(
            msg="%s still cannot read property %s after the grant (%d reads, %ds apart); Google said: %s. %s"
                % (reader.email, property_id, attempts, p["wait_delay"], first, manual),
            changed=granted, granted=granted, reader=reader.email)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=granted, granted=granted)


if __name__ == "__main__":
    main()
