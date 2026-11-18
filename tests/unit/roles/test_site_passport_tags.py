"""Run the passport role's real tag check and template without touching a server."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
ROLE = ROOT / "roles/site_passport"
LAST = "Stop when the domain origin is not declared correctly"
SECRET = "unit-test-throwaway-secret-0123456789"  # secret-lint: allow — a throwaway value
FILE = "passport.json"


def run(tmp_path, **given):
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    tasks = tasks[:next(i for i, task in enumerate(tasks) if task["name"] == LAST)]
    tasks.append({"name": "Render the body", "ansible.builtin.copy": {
        "content": "{{ lookup('ansible.builtin.template', '" + str(ROLE / "templates/passport.json.j2") + "') }}",
        "dest": str(tmp_path / FILE), "mode": "0600"}})
    variables = yaml.safe_load((ROOT / "roles/site/defaults/main.yml").read_text())
    variables.update(site_domain="example.test", site_passport_country="DE", ansible_managed="test",
                     site_passport_secret=SECRET)  # secret-lint: allow — the module's throwaway value
    variables.update(given)
    play = [{"hosts": "localhost", "gather_facts": False, "vars": variables, "tasks": tasks}]
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run([sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", "-c", "local", str(path)],
                            cwd=ROOT, env={**os.environ, "ANSIBLE_NOCOLOR": "1"}, capture_output=True, text=True)
    return result, tmp_path / FILE


@pytest.mark.parametrize("topic", ["travel", "dir", "a", "str-esc", "t2", "a" * 32])
def test_a_topic_in_the_format_is_written_under_topic(tmp_path, topic):
    result, body = run(tmp_path, site_passport_topic=topic)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(body.read_text()) == {"country": "DE", "topic": topic, "launched": None, "origin": None}


@pytest.mark.parametrize("profile", ["str-esc", "ts-esc", "gay-esc", "dat", "str-dat", "dir"])
def test_an_older_sites_profile_is_written_exactly_as_before(tmp_path, profile):
    result, body = run(tmp_path, site_passport_profile=profile, site_passport_launched="2026-01-15",
                       site_passport_origin="drop")

    assert result.returncode == 0, result.stdout + result.stderr
    assert body.read_text() == '{"country":"DE","profile":"%s","launched":"2026-01-15","origin":"drop"}\n' % profile


@pytest.mark.parametrize("tag", ["", "Travel", "travel\n", "tour ism", "str_esc", "1dir", "-dir", "а", "a" * 33, 5, ["dir"]])
@pytest.mark.parametrize("key", ["site_passport_topic", "site_passport_profile"])
def test_a_tag_outside_the_format_stops_the_role_under_either_key(tmp_path, key, tag):
    result, body = run(tmp_path, **{key: tag})

    assert result.returncode != 0
    assert "cannot be written" in result.stdout
    assert not body.exists()
    assert SECRET not in result.stdout + result.stderr


@pytest.mark.parametrize("other", [False, 0, [], {}, "x y"])
@pytest.mark.parametrize("named,other_key", [("site_passport_topic", "site_passport_profile"),
                                             ("site_passport_profile", "site_passport_topic")])
def test_a_second_key_that_is_not_empty_is_never_taken_for_absent(tmp_path, named, other_key, other):
    result, body = run(tmp_path, **{named: "travel", other_key: other})

    assert result.returncode != 0
    assert "cannot be written" in result.stdout
    assert not body.exists()


@pytest.mark.parametrize("empty", [None, ""])
def test_null_and_the_empty_string_both_mean_not_named(tmp_path, empty):
    result, body = run(tmp_path, site_passport_topic="travel", site_passport_profile=empty)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(body.read_text())["topic"] == "travel"


def test_naming_both_stops_the_role_and_says_so(tmp_path):
    result, body = run(tmp_path, site_passport_topic="travel", site_passport_profile="dir")

    assert result.returncode != 0
    assert "and it got both" in result.stdout
    assert not body.exists()


def test_naming_neither_stops_the_role_and_says_so(tmp_path):
    result, body = run(tmp_path)

    assert result.returncode != 0
    assert "and it got neither" in result.stdout
    assert not body.exists()


def test_the_closed_list_is_gone_and_the_pattern_is_the_readers_rule():
    variables = yaml.safe_load((ROOT / "roles/site/defaults/main.yml").read_text())

    assert "site_passport_profiles" not in variables
    assert variables["site_passport_tag_pattern"] == r"^[a-z][a-z0-9-]{0,31}\Z"
