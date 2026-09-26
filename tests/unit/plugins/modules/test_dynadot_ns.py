from fakes.doh import SERVFAIL, FakeDoh
from fakes.dynadot import KEY, FakeDynadot

PAIR = ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"]
PARKING = ["ns1.dynadot.com", "ns2.dynadot.com"]


def world(serve, domain, hosts):
    return [serve(FakeDoh({domain: hosts})), serve(FakeDoh({domain: hosts}))]


def args(registrar, resolvers, domain, nameservers=PAIR):
    return dict(domain=domain, nameservers=nameservers, api_key=KEY, api_url=registrar.url,
                resolvers=[r.url for r in resolvers])


def sets(registrar):
    return [r for r in registrar.requests if r.query.get("command") == "set_ns"]


def test_points_the_domain_at_the_pair(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["umzug.de"] = PARKING
    run("dynadot_ns", args(serve(dynadot), world(serve, "umzug.de", PARKING), "umzug.de"))
    assert dynadot.domains["umzug.de"] == PAIR


def test_pointing_reports_changed(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["umzug.de"] = PARKING
    assert run("dynadot_ns", args(serve(dynadot), world(serve, "umzug.de", PARKING), "umzug.de"))["changed"] is True


def test_already_resolving_leaves_the_registrar_unasked(run, serve):
    dynadot = FakeDynadot()
    registrar = serve(dynadot)
    run("dynadot_ns", args(registrar, world(serve, "angekommen.de", PAIR), "angekommen.de"))
    assert registrar.requests == []


def test_already_resolving_reports_delegated(run, serve):
    result = run("dynadot_ns", args(serve(FakeDynadot()), world(serve, "angekommen.de", PAIR), "angekommen.de"))
    assert (result["changed"], result["delegated"]) == (False, True)


def test_public_dns_that_cannot_answer_leaves_the_registrar_alone(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["dnsweg.de"] = PARKING
    registrar = serve(dynadot)
    resolvers = world(serve, "dnsweg.de", PARKING)
    resolvers[1].app.status = SERVFAIL
    run("dynadot_ns", args(registrar, resolvers, "dnsweg.de"))
    assert registrar.requests == []


def test_public_dns_that_cannot_answer_fails(run, serve):
    resolvers = world(serve, "dnsweg.de", PARKING)
    resolvers[0].outages = ["drop", "drop", "drop"]
    assert run("dynadot_ns", args(serve(FakeDynadot()), resolvers, "dnsweg.de"))["failed"] is True


def test_set_at_registrar_but_not_spread_is_not_written_again(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["wartezeit.de"] = PAIR
    registrar = serve(dynadot)
    run("dynadot_ns", args(registrar, world(serve, "wartezeit.de", PARKING), "wartezeit.de"))
    assert sets(registrar) == []


def test_set_at_registrar_but_not_spread_reports_not_delegated(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["wartezeit.de"] = PAIR
    result = run("dynadot_ns", args(serve(dynadot), world(serve, "wartezeit.de", PARKING), "wartezeit.de"))
    assert (result["changed"], result["delegated"]) == (False, False)


def test_domain_bought_elsewhere_is_not_a_failure(run, serve):
    result = run("dynadot_ns", args(serve(FakeDynadot()), world(serve, "anderswo.de", PARKING), "anderswo.de"))
    assert (result.get("failed", False), result["registrar_holds"]) == (False, False)


def test_domain_bought_elsewhere_says_where_to_set_the_pair(run, serve):
    result = run("dynadot_ns", args(serve(FakeDynadot()), world(serve, "anderswo.de", PARKING), "anderswo.de"))
    # A string before ansible-core 2.19, a structured summary after; the text is in both.
    assert "bought elsewhere" in str(result["warnings"])


def test_zone_dynadot_does_not_serve_is_not_a_failure(run, serve):
    dynadot = FakeDynadot()
    dynadot.unsupported.add("steppe.kz")
    result = run("dynadot_ns", args(serve(dynadot), world(serve, "steppe.kz", PARKING), "steppe.kz"))
    assert result["registrar_holds"] is False


def test_refused_key_fails(run, serve):
    registrar = serve(FakeDynadot("real-dynadot-key"))
    assert "invalid key" in run("dynadot_ns", args(registrar, world(serve, "schluessel.de", PARKING), "schluessel.de"))["msg"]


def test_other_refusal_is_a_failure_not_bought_elsewhere(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["gesperrt.de"] = PARKING
    dynadot.refuses_writes = "domain is locked"
    assert "domain is locked" in run("dynadot_ns", args(serve(dynadot), world(serve, "gesperrt.de", PARKING), "gesperrt.de"))["msg"]


def test_write_accepted_but_not_kept_fails(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["vergessen.de"] = PARKING
    dynadot.ignores_writes = True
    assert run("dynadot_ns", args(serve(dynadot), world(serve, "vergessen.de", PARKING), "vergessen.de"))["failed"] is True


def test_no_nameservers_is_refused_before_asking_anyone(run, serve):
    registrar = serve(FakeDynadot())
    resolvers = world(serve, "leer.de", PARKING)
    run("dynadot_ns", args(registrar, resolvers, "leer.de", nameservers=[]))
    assert registrar.requests + resolvers[0].requests == []


def test_check_mode_writes_nothing(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["probelauf.de"] = PARKING
    registrar = serve(dynadot)
    run("dynadot_ns", args(registrar, world(serve, "probelauf.de", PARKING), "probelauf.de"), check=True)
    assert sets(registrar) == []


def test_check_mode_reports_the_write_it_would_make(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["probelauf.de"] = PARKING
    assert run("dynadot_ns", args(serve(dynadot), world(serve, "probelauf.de", PARKING), "probelauf.de"), check=True)["changed"] is True


def test_nameservers_are_compared_without_case_or_dot(run, serve):
    dynadot = FakeDynadot()
    dynadot.domains["schreibweise.de"] = PAIR
    registrar = serve(dynadot)
    run("dynadot_ns", args(registrar, world(serve, "schreibweise.de", PARKING), "schreibweise.de",
                           nameservers=["ADA.ns.cloudflare.com.", "bob.NS.cloudflare.com"]))
    assert sets(registrar) == []


def test_key_does_not_leak_into_the_failure_message(run, serve):
    registrar = serve(FakeDynadot())
    registrar.outages = ["drop", "drop", "drop"]
    assert KEY not in run("dynadot_ns", args(registrar, world(serve, "geheim.de", PARKING), "geheim.de"))["msg"]
