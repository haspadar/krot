#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: uptimerobot_monitor
short_description: Keeps one UptimeRobot monitor for a site, told to someone who listens
description:
  - Uses the v3 API. v2 refuses keyword monitors on the free plan outright
    ("not allowed with your current plan"), while v3 accepts them.
  - Finds the monitor by its exact friendly name across every page of the
    account's monitors, and creates it only when none is found.
  - Refuses to create a monitor while the account has no active alert contact,
    and assigns the active contacts to an existing monitor that has none. A
    monitor keeps its own list of whom to tell; an empty one records the
    outage and tells nobody.
  - A keyword monitor alerts when the word is GONE from the page, and the
    match is case-sensitive. The word is looked for on the page before the
    monitor is made, since a monitor made for a word the page does not carry
    alerts from its first check.
  - The type of a monitor cannot be changed in place; a monitor of the other
    type is replaced only when asked to.
  - In check mode nothing is written.
options:
  url:
    description: The address to watch.
    type: str
    required: true
  friendly_name:
    description:
      - The monitor's name, and how it is found again. Kept exact, so a site's
        monitors sort together in the list a person reads.
    type: str
    required: true
  type:
    description: C(http) watches the status, C(keyword) watches a word on the page.
    type: str
    choices: [http, keyword]
    default: http
  keyword:
    description: The word that must stay on the page. Case-sensitive.
    type: str
  page_check:
    description: Look for the keyword on the page before creating or changing a keyword monitor.
    type: bool
    default: true
  replace_on_type_change:
    description: Delete a same-named monitor of the other type and create this one.
    type: bool
    default: false
  interval:
    description: Seconds between checks.
    type: int
    default: 300
  timeout:
    description: Seconds a check may take.
    type: int
    default: 30
  api_key:
    description: UptimeRobot API key.
    type: str
    required: true
  api_url:
    description: UptimeRobot v3 API address; changed only by tests.
    type: str
    default: https://api.uptimerobot.com/v3
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Alert when the profiles are gone from the front page
  haspadar.krot.uptimerobot_monitor:
    url: https://example.de/
    friendly_name: example.de (Profile)
    type: keyword
    keyword: Profil
    api_key: "{{ uptimerobot_key }}"
  delegate_to: localhost
"""

RETURN = r"""
exists:
  description: Whether the monitor exists after the run. False only in check mode.
  type: bool
  returned: always
monitor_id:
  description: UptimeRobot's id of the monitor.
  type: str
  returned: when exists
actions:
  description: What was (or in check mode would be) done — created, replaced, keyword, contacts.
  type: list
  elements: str
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import open_url

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable

API_URL = "https://api.uptimerobot.com/v3"

# v2 answered types as numbers; v3 as words. Both are read, only words are sent.
TYPES = {1: "HTTP", 2: "KEYWORD", "1": "HTTP", "2": "KEYWORD"}

# A runaway nextLink loop is not an answer either.
MOST_PAGES = 100


class Refused(Exception):
    """UptimeRobot answered and said no."""


class Robot:
    def __init__(self, key, url):
        self.url = url.rstrip("/")
        self.http = Http(self.url, headers={"Authorization": "Bearer " + key})

    def call(self, method, path, body=None):
        status, answer = self.http.call(method, path, body=body)
        if status >= 400:
            raise Refused("UptimeRobot refused %s %s (HTTP %d): %s" % (method, path.split("?", 1)[0], status, reason(answer)))
        return answer

    def every(self, path):
        """Every entry of a paged list.

        The answer carries no total, so a full page and a cut one look the
        same; only nextLink tells them apart. Reading the first page alone is
        how a site whose monitors sit past the cut reads as having none — busel
        measured it at the twenty-sixth site.
        """
        entries = []
        for _ in range(MOST_PAGES):
            answer = self.call("GET", path)
            data = answer.get("data") if isinstance(answer, dict) else None
            if not isinstance(data, list):
                raise Unreachable("UptimeRobot answered %s without a data list" % path.split("?", 1)[0])
            entries.extend(entry for entry in data if isinstance(entry, dict))
            following = answer.get("nextLink")
            if not following:
                return entries
            if not following.startswith(self.url + "/"):
                raise Unreachable("UptimeRobot's nextLink points outside its API")
            path = following[len(self.url):]
        raise Unreachable("UptimeRobot kept paging past %d pages" % MOST_PAGES)

    def monitor(self, name):
        found = [m for m in self.every("/monitors?limit=50") if m.get("friendlyName") == name]
        if len(found) > 1:
            raise Refused("%d monitors are named %s; remove the extra ones" % (len(found), name))
        return found[0] if found else None

    def contacts(self):
        # Read at the moment of writing rather than declared in config: a
        # declared list drifts from the account silently, towards nobody.
        # Compared without case — the live answer says "Active".
        return [
            dict(alertContactId=str(contact["id"]), threshold=0, recurrence=0)
            for contact in self.every("/alert-contacts")
            if contact.get("id") is not None and str(contact.get("status", "")).lower() == "active"
        ]


def reason(answer):
    if isinstance(answer, dict):
        for field in ("message", "error", "errors"):
            if answer.get(field):
                return str(answer[field])
    return "no reason given"


def kind(monitor):
    value = monitor.get("type")
    return TYPES.get(value, str(value).upper())


def assigned(monitor):
    return bool(monitor.get("assignedAlertContacts"))


def page_has(url, word):
    try:
        page = open_url(url, method="GET", timeout=30, follow_redirects="all").read()
    except Exception as error:  # the page is the site, not the API: any failure means "cannot tell"
        raise Unreachable("Could not read %s to look for the keyword: %s" % (url, error))
    return word in page.decode("utf-8", "replace")


def main():
    module = AnsibleModule(
        argument_spec=dict(
            url=dict(type="str", required=True),
            friendly_name=dict(type="str", required=True),
            type=dict(type="str", choices=["http", "keyword"], default="http"),
            keyword=dict(type="str"),
            page_check=dict(type="bool", default=True),
            replace_on_type_change=dict(type="bool", default=False),
            interval=dict(type="int", default=300),
            timeout=dict(type="int", default=30),
            api_key=dict(type="str", required=True, no_log=True),
            api_url=dict(type="str", default=API_URL),
        ),
        required_if=[("type", "keyword", ["keyword"])],
        supports_check_mode=True,
    )
    p = module.params
    wanted = p["type"].upper()
    keyword = wanted == "KEYWORD"
    robot = Robot(p["api_key"], p["api_url"])
    actions = []
    changed = False

    def keyword_fields():
        return dict(keywordType="ALERT_NOT_EXISTS", keywordCaseType="CaseSensitive", keywordValue=p["keyword"])

    try:
        contacts = robot.contacts()
        if not contacts:
            module.fail_json(msg="UptimeRobot has no active alert contact: a monitor would tell nobody", actions=actions)

        monitor = robot.monitor(p["friendly_name"])

        if monitor is not None and kind(monitor) != wanted:
            if not p["replace_on_type_change"]:
                module.fail_json(
                    msg="%s is a %s monitor and UptimeRobot cannot change a monitor's type; "
                        "set replace_on_type_change to delete and recreate it" % (p["friendly_name"], kind(monitor)),
                    actions=actions)
            actions.append("replaced")

        needs_word = keyword and (
            monitor is None or "replaced" in actions or monitor.get("keywordValue") != p["keyword"])
        if needs_word and p["page_check"] and not page_has(p["url"], p["keyword"]):
            module.fail_json(msg="%s does not carry %r (case-sensitive); the monitor would alert from its first check"
                                 % (p["url"], p["keyword"]), actions=actions)

        if monitor is None:
            actions.append("created")
        elif "replaced" not in actions:
            if keyword and monitor.get("keywordValue") != p["keyword"]:
                actions.append("keyword")
            if not assigned(monitor):
                actions.append("contacts")

        if module.check_mode or not actions:
            result = dict(exists=monitor is not None and "replaced" not in actions, actions=actions)
            if result["exists"]:
                result["monitor_id"] = str(monitor.get("id"))
            module.exit_json(changed=bool(actions), **result)

        if "replaced" in actions:
            robot.call("DELETE", "/monitors/%s" % monitor["id"])
            changed = True
            monitor = None
        if monitor is None:
            body = dict(type=wanted, url=p["url"], friendlyName=p["friendly_name"], interval=p["interval"],
                        timeout=p["timeout"], assignedAlertContacts=contacts)
            if keyword:
                body.update(keyword_fields())
            robot.call("POST", "/monitors", body)
            changed = True
        else:
            patch = {}
            if "keyword" in actions:
                patch.update(keyword_fields())
            if "contacts" in actions:
                patch["assignedAlertContacts"] = contacts
            robot.call("PATCH", "/monitors/%s" % monitor["id"], patch)
            changed = True

        # The write's answer is not the proof; the monitor as the list shows it is.
        monitor = robot.monitor(p["friendly_name"])
        if monitor is None:
            module.fail_json(msg="UptimeRobot accepted %s but does not list it" % p["friendly_name"], changed=True, actions=actions)
        if kind(monitor) != wanted or (keyword and monitor.get("keywordValue") != p["keyword"]):
            module.fail_json(msg="UptimeRobot lists %s other than it was written" % p["friendly_name"], changed=True, actions=actions)
        if "assignedAlertContacts" in monitor and not assigned(monitor):
            module.fail_json(msg="UptimeRobot lists %s with nobody to tell" % p["friendly_name"], changed=True, actions=actions)
        module.exit_json(changed=True, exists=True, monitor_id=str(monitor.get("id")), actions=actions)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=changed, actions=actions)


if __name__ == "__main__":
    main()
