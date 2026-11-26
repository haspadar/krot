# MIT License
"""Validate the non-secret GA4 assignment exported in a site's passport."""

from datetime import date
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ansible.errors import AnsibleFilterError

FIELDS = {"account_id", "property_id", "stream_id", "measurement_id", "owner", "timezone", "since"}


def valid_google_analytics(value):
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise AnsibleFilterError("site_passport_google_analytics must be null or an object with exactly "
                                 + ", ".join(sorted(FIELDS)))
    if any(not isinstance(field, str) for field in value.values()):
        raise AnsibleFilterError("Every google_analytics field must be a string")
    for field in ("account_id", "property_id", "stream_id"):
        if not re.fullmatch(r"[0-9]+", value[field]):
            raise AnsibleFilterError("google_analytics.%s must be a numeric ID" % field)
    if not re.fullmatch(r"G-[A-Z0-9]+", value["measurement_id"]):
        raise AnsibleFilterError("google_analytics.measurement_id must be a G- measurement ID")
    local, separator, host = value["owner"].rpartition("@")
    if (not separator or len(value["owner"]) > 254 or len(local) > 64
            or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*", local)
            or len(host) > 253 or len(host.split(".")) < 2
            or any(not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                   for label in host.split("."))
            or host.lower().endswith(".gserviceaccount.com")):
        raise AnsibleFilterError("google_analytics.owner must name the human GSC owner")
    try:
        if value["timezone"] in ("localtime", "posixrules") or value["timezone"].startswith(("posix/", "right/")):
            raise ValueError
        ZoneInfo(value["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise AnsibleFilterError("google_analytics.timezone must be an existing IANA timezone") from None
    try:
        if date.fromisoformat(value["since"]).isoformat() != value["since"]:
            raise ValueError
    except ValueError:
        raise AnsibleFilterError("google_analytics.since must be a calendar date in YYYY-MM-DD") from None
    return True


class FilterModule:
    def filters(self):
        return {"valid_google_analytics": valid_google_analytics}
