"""The molecule fake's wiring: resolvers and zone status follow the registrar."""

import json
import urllib.error
import urllib.request

import pytest

from fakes.cloudflare import TOKEN
from fakes.dynadot import KEY
from fakes.launch import DOMAIN, PARKING, Launch


def send(server, method, path, body):
    request = urllib.request.Request(server.url + path, method=method, data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def get(server, path, headers=None):
    request = urllib.request.Request(server.url + path, headers=headers or {})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def create_zone(server):
    request = urllib.request.Request(server.url + "/cloudflare/zones", method="POST",
                                     data=json.dumps({"name": DOMAIN, "type": "full"}).encode(),
                                     headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["result"]


def point(server, hosts):
    query = "&".join("ns%d=%s" % (i, host) for i, host in enumerate(hosts))
    get(server, "/dynadot/?key=%s&command=set_ns&domain=%s&%s" % (KEY, DOMAIN, query))


def zone_status(server):
    return get(server, "/cloudflare/zones?name=" + DOMAIN, {"Authorization": "Bearer " + TOKEN})["result"][0]["status"]


def test_resolvers_answer_what_the_registrar_holds(serve):
    server = serve(Launch("http://fakes.test"))
    answer = get(server, "/doh/google/resolve?name=%s&type=NS" % DOMAIN)
    assert [a["data"] for a in answer["Answer"]] == [host + "." for host in PARKING]


def test_new_zone_waits_while_the_domain_is_parked(serve):
    server = serve(Launch("http://fakes.test"))
    create_zone(server)
    assert zone_status(server) == "pending"


def test_zone_turns_active_once_the_registrar_points_at_it(serve):
    server = serve(Launch("http://fakes.test"))
    point(server, create_zone(server)["name_servers"])
    assert zone_status(server) == "active"


def test_state_lists_what_the_launch_created(serve):
    server = serve(Launch("http://fakes.test"))
    create_zone(server)
    assert [z["name"] for z in get(server, "/_state")["zones"]] == [DOMAIN]


def status(server, path):
    try:
        with urllib.request.urlopen(server.url + path) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def launched(server, open_it=True):
    """A zone the registrar points at, with the apex proxied to the machine."""
    zone = create_zone(server)
    point(server, zone["name_servers"])
    send(server, "POST", "/cloudflare/zones/%s/dns_records" % zone["id"],
         {"type": "A", "name": DOMAIN, "content": "203.0.113.7", "proxied": True})
    if open_it:
        send(server, "POST", "/_open", {})
    return zone


def test_site_is_unreachable_without_its_record(serve):
    server = serve(Launch("http://fakes.test"))
    point(server, create_zone(server)["name_servers"])
    send(server, "POST", "/_open", {})
    assert status(server, "/site/") == 530


def test_site_asks_for_a_password_until_the_project_opens_it(serve):
    server = serve(Launch("http://fakes.test"))
    launched(server, open_it=False)
    assert status(server, "/site/sitemap.xml") == 401


def test_opened_site_answers_through_cloudflare(serve):
    server = serve(Launch("http://fakes.test"))
    launched(server)
    with urllib.request.urlopen(server.url + "/site/") as response:
        assert response.headers["CF-Ray"]


def test_www_needs_a_record_of_its_own(serve):
    server = serve(Launch("http://fakes.test"))
    launched(server)
    assert status(server, "/site-www/") == 530


def test_google_finds_no_proof_outside_the_zone(serve):
    launch = Launch("http://fakes.test")
    server = serve(launch)
    launched(server)
    launch.proofs()
    assert launch.google.dns_visible_after == 1


def test_google_finds_the_proof_in_an_active_zone(serve):
    launch = Launch("http://fakes.test")
    server = serve(launch)
    zone = launched(server)
    send(server, "POST", "/cloudflare/zones/%s/dns_records" % zone["id"],
         {"type": "TXT", "name": DOMAIN, "content": '"google-site-verification=v-krot-launch"'})
    launch.proofs()
    assert launch.google.dns_visible_after == 0


def test_write_is_kept_under_the_run_that_sent_it(serve):
    server = serve(Launch("http://fakes.test"))
    send(server, "POST", "/_run", {"mode": "check"})
    send(server, "POST", "/_run", {"mode": "converge"})
    create_zone(server)
    assert [len(r["writes"]) for r in get(server, "/_state")["runs"]] == [0, 1]


def test_registrar_change_counts_as_a_write(serve):
    server = serve(Launch("http://fakes.test"))
    send(server, "POST", "/_run", {"mode": "converge"})
    point(server, ["ns1.example.net", "ns2.example.net"])
    assert get(server, "/_state")["runs"][0]["writes"] == ["GET /dynadot/"]


def test_reading_the_registrar_is_not_a_write(serve):
    server = serve(Launch("http://fakes.test"))
    send(server, "POST", "/_run", {"mode": "check"})
    get(server, "/dynadot/?key=%s&command=get_ns&domain=%s" % (KEY, DOMAIN))
    assert get(server, "/_state")["runs"][0]["writes"] == []


def test_asking_google_for_the_proof_is_not_a_write(serve):
    server = serve(Launch("http://fakes.test"))
    send(server, "POST", "/_run", {"mode": "check"})
    # Refused for want of a token; what matters is how the request was filed.
    with pytest.raises(urllib.error.HTTPError):
        send(server, "POST", "/google/siteVerification/v1/token", {})
    assert get(server, "/_state")["runs"][0]["writes"] == []
