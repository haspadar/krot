# -*- coding: utf-8 -*-
# MIT License
"""The Cloudflare v4 API as the site-launch modules need it."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable

API_URL = "https://api.cloudflare.com/client/v4"

# Shared by every Cloudflare module, so the token and the address are spelled
# the same way in all of them.
ARGUMENTS = dict(
    api_token=dict(type="str", required=True, no_log=True),
    api_url=dict(type="str", default=API_URL),
)


class Refused(Exception):
    """Cloudflare answered and said no; `status` is the HTTP status it said it with."""

    def __init__(self, message, status=None):
        super(Refused, self).__init__(message)
        self.status = status


class Cloudflare:
    def __init__(self, token, url=API_URL):
        self.http = Http(url, headers={"Authorization": "Bearer " + token})

    def call(self, method, path, query=None, body=None):
        return self._answer(method, path, query, body)["result"]

    def pages(self, path, per_page=50, query=None):
        """Every item of a paginated list, however many pages it takes.

        Stops on the page Cloudflare names last (result_info.total_pages) or, when it names
        none, on the first empty one — never on a short page, since a server that caps
        per_page below the asked size would end the walk with items still unread.
        """
        items, page = [], 1
        while True:
            answer = self._answer("GET", path, dict(query or {}, per_page=per_page, page=page))
            found = answer["result"]
            if not isinstance(found, list):
                raise Unreachable("Cloudflare answered %s without a list" % path)
            items.extend(found)
            last = (answer.get("result_info") or {}).get("total_pages")
            if not found or (isinstance(last, int) and page >= last):
                return items
            page += 1
            if page > 1000:
                raise Unreachable("Cloudflare kept answering %s with more pages than any account has" % path)

    def _answer(self, method, path, query=None, body=None):
        status, answer = self.http.call(method, path, query, body)
        if not isinstance(answer, dict):
            raise Unreachable("Cloudflare answered %s %s with no body (HTTP %d)" % (method, path, status))
        # 200 with success:false is how Cloudflare normally says no, so the
        # status line proves nothing and the flag is what gets read.
        if answer.get("success") is not True:
            errors = answer.get("errors") or [{}]
            message = errors[0].get("message") if isinstance(errors[0], dict) else None
            raise Refused("Cloudflare refused %s %s (HTTP %d): %s" % (method, path, status, message or "no reason given"),
                          status)
        if "result" not in answer:
            raise Unreachable("Cloudflare answered %s %s without a result" % (method, path))
        return answer

    def zones(self, domain, account_id=None):
        query = {"name": domain}
        if account_id:
            query["account.id"] = account_id
        found = self.call("GET", "/zones", query)
        if not isinstance(found, list):
            raise Unreachable("Cloudflare answered the zone lookup without a list")
        return found

    def settings(self, zone_id):
        """Every setting of the zone in one request, as name to value."""
        result = self.call("GET", "/zones/%s/settings" % zone_id)
        if not isinstance(result, list):
            raise Unreachable("Cloudflare answered the zone settings without a list")
        return dict((item["id"], item.get("value")) for item in result if isinstance(item, dict) and "id" in item)


def comparable(value):
    """One spelling for a setting's value, whatever type the API stores it as.

    browser_cache_ttl comes back as a number and would never equal "0" read as
    text — the module would then write it on every run and report a change.
    """
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def sendable(value):
    # Cloudflare refuses "0" where it wants 0, and the refusal names a field the
    # caller believes it set.
    text = comparable(value)
    return int(text) if text.lstrip("-").isdigit() else text
