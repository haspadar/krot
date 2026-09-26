# -*- coding: utf-8 -*-
# MIT License
"""Where a domain is delegated, as public resolvers see it.

Asked over DNS-over-HTTPS rather than through the machine's own resolver: the
answer is JSON, so it goes through the same HTTP layer as every other API here,
the molecule fake can answer it, and nothing needs dnspython.

Two independent resolvers, and both must answer. One resolver's cache can hold
the old delegation for hours after the other has the new one, and a record
written into a zone the world does not resolve through yet is the one that
publishes the origin's address in DNS history for good.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable

RESOLVERS = [
    "https://dns.google/resolve",
    "https://cloudflare-dns.com/dns-query",
]

NOERROR = 0
NXDOMAIN = 3
NS = 2


def normalised(host):
    return host.strip().lower().rstrip(".")


def ask(resolver, domain):
    """The NS set one resolver reports for the domain.

    NXDOMAIN is an answer — a domain delegated nowhere — and comes back empty.
    Any other status (SERVFAIL above all) is a resolver that could not say, and
    is raised rather than read as "no nameservers".
    """
    http = Http(resolver, headers={"Accept": "application/dns-json"})
    status, answer = http.call("GET", "", {"name": domain, "type": "NS"})
    if status != 200 or not isinstance(answer, dict) or not isinstance(answer.get("Status"), int):
        raise Unreachable("%s did not answer for %s (HTTP %d)" % (resolver, domain, status))
    if answer["Status"] == NXDOMAIN:
        return []
    if answer["Status"] != NOERROR:
        raise Unreachable("%s could not resolve %s (DNS status %d)" % (resolver, domain, answer["Status"]))
    records = answer.get("Answer") or []
    if not isinstance(records, list):
        raise Unreachable("%s answered %s with a malformed Answer" % (resolver, domain))
    return sorted(set(
        normalised(record["data"]) for record in records
        if isinstance(record, dict) and record.get("type") == NS and isinstance(record.get("data"), str)
    ))


def answers(domain, resolvers=None):
    """Resolver to NS list, for every resolver. Raises if any of them cannot say."""
    return dict((resolver, ask(resolver, domain)) for resolver in (resolvers or RESOLVERS))


def delegated(found, expected):
    """True when every resolver sees exactly the expected nameservers."""
    wanted = set(normalised(host) for host in expected)
    return bool(found) and all(set(hosts) == wanted for hosts in found.values())
