"""Runs playbooks/search_console_access.yml with ansible-playbook against the Google fake.

A playbook's report and its exit code are what an operator reads, so they are what is
asserted: a module test cannot see the loop, the check mode switch or the final assert.
"""

import json
import os
import subprocess
import sys

import pytest

from fakes.google import EMAIL, FakeGoogle, FakeTokens, service_account

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PLAYBOOK = os.path.join(ROOT, "playbooks", "search_console_access.yml")
COLLECTOR = "sammler@krot-units.iam.gserviceaccount.com"


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


@pytest.fixture
def playbook(tmp_path, tokens):
    """Runs the playbook with the given domains and extra vars; returns (exit code, output)."""
    collections = tmp_path / "collections" / "ansible_collections" / "haspadar"
    collections.mkdir(parents=True)
    os.symlink(ROOT, collections / "krot")

    def run(server, domains, flags=(), **extra):
        variables = dict(search_console_domains=domains,
                         site_google_service_account=service_account(tokens.uri),
                         site_search_console_reader_service_account=service_account(tokens.uri, COLLECTOR),
                         site_google_token_uri=tokens.uri, site_google_api_url=server.url, **extra)
        path = tmp_path / "vars.json"
        path.write_text(json.dumps(variables))
        env = dict(os.environ, ANSIBLE_COLLECTIONS_PATH=str(tmp_path / "collections"),
                   ANSIBLE_LOCALHOST_WARNING="False", ANSIBLE_NOCOLOR="1")
        done = subprocess.run([sys.executable, "-m", "ansible.cli.playbook", PLAYBOOK, "-e", "@" + str(path)]
                              + list(flags),
                              capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=300)
        return done.returncode, done.stdout + done.stderr

    return run


def seeded():
    google = FakeGoogle()
    google.verified("gehoert.de", [EMAIL, COLLECTOR])
    google.others[COLLECTOR] = {"sc-domain:gehoert.de": "siteOwner"}
    google.verified("luecke.de")
    google.verified("fremd.de", ["fremd@x.iam.gserviceaccount.com"])
    return google


def test_every_domain_owned_passes(serve, playbook):
    code, out = playbook(serve(seeded()), ["gehoert.de"])
    assert code == 0, out


def test_a_domain_not_owned_fails_the_run(serve, playbook):
    code, out = playbook(serve(seeded()), ["gehoert.de", "luecke.de"])
    assert (code != 0, "luecke.de" in out.split("Not owned by the collecting key")[-1]) == (True, True), out


def test_the_report_says_the_launching_key_can_grant(serve, playbook):
    _, out = playbook(serve(seeded()), ["luecke.de"])
    assert "the launching key can grant it" in out, out


def test_the_report_gives_the_manual_step_where_the_launching_key_cannot(serve, playbook):
    _, out = playbook(serve(seeded()), ["fremd.de"])
    assert "NOT owned by %s: the launching key is not an owner" % COLLECTOR in out, out


def test_checking_writes_nothing(serve, playbook):
    server = serve(seeded())
    playbook(server, ["gehoert.de", "luecke.de", "fremd.de"])
    assert server.writes() == []


def test_a_domain_google_refuses_to_answer_about_fails_the_run(serve, playbook):
    google = seeded()
    google.disabled_scopes = {"https://www.googleapis.com/auth/webmasters"}
    code, out = playbook(serve(google), ["gehoert.de"])
    assert (code != 0, "FAILED: " in out) == (True, True), out


def test_grant_makes_the_collecting_key_an_owner(serve, playbook):
    google = seeded()
    code, out = playbook(serve(google), ["gehoert.de", "luecke.de"], search_console_access_grant=True)
    assert (code, google.others[COLLECTOR].get("sc-domain:luecke.de")) == (0, "siteOwner"), out


def test_check_mode_wins_over_the_grant_flag(serve, playbook):
    server = serve(seeded())
    playbook(server, ["luecke.de"], flags=["--check"], search_console_access_grant=True)
    assert server.writes() == []


def test_grant_leaves_domains_it_cannot_grant_failing(serve, playbook):
    google = seeded()
    code, _ = playbook(serve(google), ["fremd.de"], search_console_access_grant=True)
    assert (code != 0, google.resources["dns://fremd.de"]) == (True, ["fremd@x.iam.gserviceaccount.com"])


def test_no_domains_fails_the_run(serve, playbook):
    code, out = playbook(serve(seeded()), [])
    assert (code != 0, "Give search_console_domains" in out) == (True, True), out
