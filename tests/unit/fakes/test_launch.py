"""The molecule fake's wiring: resolvers and zone status follow the registrar."""

import json
import urllib.request

from fakes.cloudflare import TOKEN
from fakes.dynadot import KEY
from fakes.launch import DOMAIN, PARKING, Launch


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


def test_site_answers_through_cloudflare(serve):
    server = serve(Launch("http://fakes.test"))
    with urllib.request.urlopen(server.url + "/site/") as response:
        assert response.headers["CF-Ray"]
