from fakes.doh import SERVFAIL, FakeDoh

PAIR = ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"]
OLD = ["ns1.dynadot.com", "ns2.dynadot.com"]


def args(domain, *resolvers):
    return dict(domain=domain, nameservers=PAIR, resolvers=[r.url for r in resolvers])


def test_delegated_when_both_resolvers_agree(run, serve):
    first, second = serve(FakeDoh({"fertig.de": PAIR})), serve(FakeDoh({"fertig.de": PAIR}))
    assert run("dns_delegation", args("fertig.de", first, second))["delegated"] is True


def test_not_delegated_while_resolvers_disagree(run, serve):
    first, second = serve(FakeDoh({"unterwegs.de": PAIR})), serve(FakeDoh({"unterwegs.de": OLD}))
    assert run("dns_delegation", args("unterwegs.de", first, second))["delegated"] is False


def test_reports_what_each_resolver_saw(run, serve):
    first, second = serve(FakeDoh({"unterwegs.de": PAIR})), serve(FakeDoh({"unterwegs.de": OLD}))
    result = run("dns_delegation", args("unterwegs.de", first, second))
    assert result["answers"] == {first.url: PAIR, second.url: OLD}


def test_never_reports_a_change(run, serve):
    resolver = serve(FakeDoh({"lesen.de": PAIR}))
    assert run("dns_delegation", args("lesen.de", resolver))["changed"] is False


def test_resolver_that_cannot_answer_fails_instead_of_saying_no(run, serve):
    doh = FakeDoh({"stumm.de": PAIR})
    doh.status = SERVFAIL
    assert run("dns_delegation", args("stumm.de", serve(doh)))["failed"] is True


def test_works_in_check_mode(run, serve):
    resolver = serve(FakeDoh({"pruefung.de": PAIR}))
    assert run("dns_delegation", args("pruefung.de", resolver), check=True)["delegated"] is True
