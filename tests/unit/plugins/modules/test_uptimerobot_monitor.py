from fakes.uptimerobot import KEY, FakePage, FakeUptimeRobot


def args(server, name, url="https://example.invalid/", **extra):
    return dict(url=url, friendly_name=name, api_key=KEY, api_url=server.url, **extra)


def keyword_args(server, page, name, word, **extra):
    return args(server, name, url=page.url + "/", type="keyword", keyword=word, **extra)


def test_creates_absent_http_monitor(run, serve):
    robot = FakeUptimeRobot()
    run("uptimerobot_monitor", args(serve(robot), "wachhund.de"))
    assert [m["friendlyName"] for m in robot.monitors] == ["wachhund.de"]


def test_new_monitor_tells_the_active_contacts(run, serve):
    robot = FakeUptimeRobot()
    run("uptimerobot_monitor", args(serve(robot), "wachhund.de"))
    assert robot.monitors[0]["assignedAlertContacts"] == [dict(alertContactId="101", threshold=0, recurrence=0)]


def test_paused_contact_is_not_assigned(run, serve):
    robot = FakeUptimeRobot()
    robot.contacts.append({"id": 102, "status": "Paused"})
    run("uptimerobot_monitor", args(serve(robot), "pausiert.de"))
    assert [c["alertContactId"] for c in robot.monitors[0]["assignedAlertContacts"]] == ["101"]


def test_no_active_contact_blocks_before_writing(run, serve):
    robot = FakeUptimeRobot()
    robot.contacts = [{"id": 101, "status": "Paused"}]
    server = serve(robot)
    run("uptimerobot_monitor", args(server, "stumm.de"))
    assert server.writes() == []


def test_no_active_contact_says_nobody_would_hear(run, serve):
    robot = FakeUptimeRobot()
    robot.contacts = []
    assert "tell nobody" in run("uptimerobot_monitor", args(serve(robot), "stumm.de"))["msg"]


def test_contacts_on_a_later_page_are_found(run, serve):
    robot = FakeUptimeRobot()
    robot.page_size = 1
    robot.contacts = [{"id": 101, "status": "Paused"}, {"id": 103, "status": "Active"}]
    run("uptimerobot_monitor", args(serve(robot), "blaettern.de"))
    assert [c["alertContactId"] for c in robot.monitors[0]["assignedAlertContacts"]] == ["103"]


def test_keyword_monitor_alerts_when_the_word_is_gone(run, serve):
    robot = FakeUptimeRobot()
    page = serve(FakePage("<h1>Profile</h1>"))
    run("uptimerobot_monitor", keyword_args(serve(robot), page, "profile.de (Profile)", "Profile"))
    assert robot.monitors[0]["keywordType"] == "ALERT_NOT_EXISTS"


def test_keyword_monitor_is_case_sensitive(run, serve):
    robot = FakeUptimeRobot()
    page = serve(FakePage("<h1>Profile</h1>"))
    run("uptimerobot_monitor", keyword_args(serve(robot), page, "profile.de (Profile)", "Profile"))
    assert robot.monitors[0]["keywordCaseType"] == "CaseSensitive"


def test_word_missing_from_the_page_blocks_creation(run, serve):
    robot = FakeUptimeRobot()
    server = serve(robot)
    page = serve(FakePage("<h1>Wartung</h1>"))
    run("uptimerobot_monitor", keyword_args(server, page, "leer.de (Profile)", "Profile"))
    assert server.writes() == []


def test_word_check_on_the_page_is_case_sensitive(run, serve):
    page = serve(FakePage("<h1>profile</h1>"))
    result = run("uptimerobot_monitor", keyword_args(serve(FakeUptimeRobot()), page, "klein.de (Profile)", "Profile"))
    assert "case-sensitive" in result["msg"]


def test_unreadable_page_blocks_creation(run, serve):
    robot = FakeUptimeRobot()
    server = serve(robot)
    page = serve(FakePage("<h1>Profile</h1>"))
    page.outages = ["drop"]
    run("uptimerobot_monitor", keyword_args(server, page, "offline.de (Profile)", "Profile"))
    assert server.writes() == []


def test_existing_monitor_is_not_written(run, serve):
    robot = FakeUptimeRobot()
    robot.add_monitor("vorhanden.de")
    server = serve(robot)
    run("uptimerobot_monitor", args(server, "vorhanden.de"))
    assert server.writes() == []


def test_second_run_is_unchanged(run, serve):
    server = serve(FakeUptimeRobot())
    run("uptimerobot_monitor", args(server, "zweimal.de"))
    assert run("uptimerobot_monitor", args(server, "zweimal.de"))["changed"] is False


def test_monitor_past_the_first_page_is_found(run, serve):
    robot = FakeUptimeRobot()
    robot.page_size = 2
    for name in ("aal.de", "barsch.de", "dorsch.de"):
        robot.add_monitor(name)
    run("uptimerobot_monitor", args(serve(robot), "dorsch.de"))
    assert [m["friendlyName"] for m in robot.monitors].count("dorsch.de") == 1


def test_name_is_matched_exactly(run, serve):
    robot = FakeUptimeRobot()
    robot.add_monitor("wache.de (Profile)", type_="KEYWORD", keyword="Profile")
    run("uptimerobot_monitor", args(serve(robot), "wache.de"))
    assert sorted(m["friendlyName"] for m in robot.monitors) == ["wache.de", "wache.de (Profile)"]


def test_other_type_is_refused_without_replacement(run, serve):
    robot = FakeUptimeRobot()
    robot.add_monitor("wechsel.de (Profile)")
    server = serve(robot)
    page = serve(FakePage("Profile"))
    run("uptimerobot_monitor", keyword_args(server, page, "wechsel.de (Profile)", "Profile"))
    assert server.writes() == []


def test_other_type_explains_it_cannot_be_changed(run, serve):
    robot = FakeUptimeRobot()
    robot.add_monitor("wechsel.de (Profile)")
    page = serve(FakePage("Profile"))
    result = run("uptimerobot_monitor", keyword_args(serve(robot), page, "wechsel.de (Profile)", "Profile"))
    assert "cannot change" in result["msg"]


def test_other_type_is_recreated_when_asked(run, serve):
    robot = FakeUptimeRobot()
    robot.add_monitor("ersatz.de (Profile)")
    page = serve(FakePage("Profile"))
    run("uptimerobot_monitor", keyword_args(serve(robot), page, "ersatz.de (Profile)", "Profile",
                                            replace_on_type_change=True))
    assert [m["type"] for m in robot.monitors] == ["KEYWORD"]


def test_changed_keyword_is_patched_in_place(run, serve):
    robot = FakeUptimeRobot()
    old = robot.add_monitor("neuwort.de (Profile)", type_="KEYWORD", keyword="Anzeigen")
    page = serve(FakePage("Profile"))
    run("uptimerobot_monitor", keyword_args(serve(robot), page, "neuwort.de (Profile)", "Profile"))
    assert (old["id"], old["keywordValue"]) == (robot.monitors[0]["id"], "Profile")


def test_monitor_telling_nobody_gets_the_contacts(run, serve):
    robot = FakeUptimeRobot()
    silent = robot.add_monitor("berlindame.de", contacts=False)
    run("uptimerobot_monitor", args(serve(robot), "berlindame.de"))
    assert [c["alertContactId"] for c in silent["assignedAlertContacts"]] == ["101"]


def test_check_mode_writes_nothing(run, serve):
    robot = FakeUptimeRobot()
    robot.add_monitor("probe.de", contacts=False)
    server = serve(robot)
    run("uptimerobot_monitor", args(server, "probe.de"), check=True)
    assert server.writes() == []


def test_check_mode_says_what_it_would_do(run, serve):
    robot = FakeUptimeRobot()
    robot.add_monitor("probe.de", contacts=False)
    assert run("uptimerobot_monitor", args(serve(robot), "probe.de"), check=True)["actions"] == ["contacts"]


def test_unreadable_monitor_list_is_not_read_as_no_monitor(run, serve):
    server = serve(FakeUptimeRobot())
    server.outages = [None, 503, 503, 503]
    run("uptimerobot_monitor", args(server, "stoerung.de"))
    assert server.writes() == []


def test_creation_whose_answer_was_lost_is_not_repeated(run, serve):
    robot = FakeUptimeRobot()
    server = serve(robot)
    server.outages = [None, None, "lost"]
    run("uptimerobot_monitor", args(server, "antwortweg.de"))
    assert len(robot.monitors) == 1


def test_wrong_key_fails(run, serve):
    assert run("uptimerobot_monitor", args(serve(FakeUptimeRobot("other-ur-key")), "fremd.de"))["failed"] is True


def test_key_does_not_leak_into_the_failure(run, serve):
    server = serve(FakeUptimeRobot())
    server.outages = ["drop", "drop", "drop"]
    assert KEY not in run("uptimerobot_monitor", args(server, "geheim.de"))["msg"]
