from fakes.umami import PASSWORD, USERNAME, FakeUmami


def args(server, domain, base="/counter", pw=PASSWORD):
    return {"domain": domain, "api_url": server.url + base, "username": USERNAME, "password": pw}


def test_creates_absent_website(run, serve):
    umami = FakeUmami()
    run("umami_website", args(serve(umami), "zaehlwerk.de"))
    assert [site["domain"] for site in umami.websites] == ["zaehlwerk.de"]


def test_returns_the_id_umami_lists(run, serve):
    umami = FakeUmami()
    result = run("umami_website", args(serve(umami), "zaehlwerk.de"))
    assert result["website_id"] == umami.websites[0]["id"]


def test_existing_website_is_not_created_again(run, serve):
    umami = FakeUmami()
    umami.add_website("besucher.de")
    server = serve(umami)
    run("umami_website", args(server, "besucher.de"))
    assert [r.path for r in server.writes()] == ["/counter/api/auth/login"]


def test_existing_website_reports_unchanged(run, serve):
    umami = FakeUmami()
    umami.add_website("besucher.de")
    assert run("umami_website", args(serve(umami), "besucher.de"))["changed"] is False


def test_second_run_is_unchanged(run, serve):
    server = serve(FakeUmami())
    run("umami_website", args(server, "zweiterlauf.de"))
    assert run("umami_website", args(server, "zweiterlauf.de"))["changed"] is False


def test_bare_list_of_older_umami_is_read(run, serve):
    umami = FakeUmami()
    umami.bare_list = True
    umami.add_website("altversion.de")
    assert run("umami_website", args(serve(umami), "altversion.de"))["changed"] is False


def test_substring_match_is_not_the_site(run, serve):
    umami = FakeUmami()
    umami.add_website("myshop.de")
    run("umami_website", args(serve(umami), "shop.de"))
    assert sorted(site["domain"] for site in umami.websites) == ["myshop.de", "shop.de"]


def test_unrecognised_listing_is_not_read_as_no_website(run, serve):
    umami = FakeUmami()
    umami.broken_listing = True
    server = serve(umami)
    run("umami_website", args(server, "fremdform.de"))
    assert [r.path for r in server.writes()] == ["/counter/api/auth/login"]


def test_missing_base_path_is_named_in_the_failure(run, serve):
    result = run("umami_website", args(serve(FakeUmami()), "ohnepfad.de", base=""))
    assert "base path" in result["msg"]


def test_refused_login_fails(run, serve):
    assert run("umami_website", args(serve(FakeUmami()), "falsch.de", pw="wrong-pass"))["failed"] is True


def test_check_mode_creates_nothing(run, serve):
    umami = FakeUmami()
    run("umami_website", args(serve(umami), "trocken.de"), check=True)
    assert umami.websites == []


def test_check_mode_reports_it_would_create(run, serve):
    result = run("umami_website", args(serve(FakeUmami()), "trocken.de"), check=True)
    assert (result["changed"], result["exists"]) == (True, False)


def test_accepted_but_not_listed_fails(run, serve):
    umami = FakeUmami()
    umami.hides_new = True
    assert "does not list" in run("umami_website", args(serve(umami), "verschwunden.de"))["msg"]


def test_creation_whose_answer_was_lost_is_not_repeated(run, serve):
    umami = FakeUmami()
    server = serve(umami)
    server.outages = [None, None, "lost"]
    run("umami_website", args(server, "antwortweg.de"))
    assert len(umami.websites) == 1


def test_password_does_not_leak_into_the_failure(run, serve):
    server = serve(FakeUmami())
    server.outages = ["drop", "drop", "drop"]
    assert PASSWORD not in run("umami_website", args(server, "geheim.de"))["msg"]
