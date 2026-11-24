"""Run site_analytics' real Web Analytics task, as a consumer's variables would reach it.

The module's own tests prove what it does to a record; whether the role switches it on only
when asked — and asks the right zone and account — is a line no module test fails without.
"""

import os
from pathlib import Path
import subprocess
import sys

import yaml

from fakes.cloudflare import DEFAULT_ACCOUNT, TOKEN, FakeCloudflare

ROOT = Path(__file__).resolve().parents[3]
STEP = "Turn Cloudflare Web Analytics on for every visitor"


def run(tmp_path, server, zone, **given):
    tasks = [t for t in yaml.safe_load((ROOT / "roles/site_analytics/tasks/main.yml").read_text())
             if t["name"] == STEP]
    # The consumer's inventory does not see the role's defaults dictionary key by key: it passes
    # site_analytics whole, so the defaults file is the base and the test replaces the key as a
    # consumer would.
    variables = yaml.safe_load((ROOT / "roles/site/defaults/main.yml").read_text())
    variables.update(site_cloudflare_token=TOKEN, site_cloudflare_api_url=server.url,
                     site_dns_zone_found={"exists": True, "zone_id": zone["id"]})
    variables.update(given)
    play = [{"hosts": "localhost", "gather_facts": False, "vars": variables, "tasks": tasks}]
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump(play))
    collections = tmp_path / "collections" / "ansible_collections" / "haspadar"
    collections.mkdir(parents=True, exist_ok=True)
    if not (collections / "krot").exists():
        (collections / "krot").symlink_to(ROOT)
    env = {**os.environ, "ANSIBLE_NOCOLOR": "1", "ANSIBLE_COLLECTIONS_PATH": str(tmp_path / "collections")}
    return subprocess.run([sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", "-c", "local", str(path)],
                          cwd=tmp_path, env=env, capture_output=True, text=True)


def lite_zone(cloudflare, name="analytics-unit.de"):
    return cloudflare.add_zone(name)


def held(cloudflare, zone):
    return next(e for e in cloudflare.rum if e["ruleset"]["zone_tag"] == zone["id"])["ruleset"]["lite"]


def test_the_dictionary_a_consumer_passes_without_the_key_leaves_cloudflare_alone(tmp_path, serve):
    cloudflare = FakeCloudflare()
    zone = lite_zone(cloudflare)
    server = serve(cloudflare)
    result = run(tmp_path, server, zone, site_analytics={"umami": False})
    assert (result.returncode, server.requests, held(cloudflare, zone)) == (0, [], True)


def test_the_defaults_alone_leave_cloudflare_alone(tmp_path, serve):
    cloudflare = FakeCloudflare()
    zone = lite_zone(cloudflare)
    server = serve(cloudflare)
    run(tmp_path, server, zone)
    assert server.requests == []


def test_the_switch_brings_the_zones_record_to_the_full_form(tmp_path, serve):
    cloudflare = FakeCloudflare()
    zone = lite_zone(cloudflare)
    result = run(tmp_path, serve(cloudflare), zone, site_analytics={"umami": False, "cloudflare_web_analytics": True})
    assert (result.returncode, held(cloudflare, zone)) == (0, False), result.stdout + result.stderr


def test_a_second_run_changes_nothing(tmp_path, serve):
    cloudflare = FakeCloudflare()
    zone = lite_zone(cloudflare)
    server = serve(cloudflare)
    given = {"site_analytics": {"umami": False, "cloudflare_web_analytics": True}}
    first = run(tmp_path, server, zone, **given)
    second = run(tmp_path, server, zone, **given)
    # "changed=0" is also in the recap of a run that failed: the exit code and failed=0 are what say it ran.
    assert (first.returncode, second.returncode, "changed=0" in second.stdout, "failed=0" in second.stdout) == (0, 0, True, True)


def test_the_account_the_inventory_names_is_the_one_asked(tmp_path, serve):
    cloudflare = FakeCloudflare()
    zone = lite_zone(cloudflare)
    server = serve(cloudflare)
    run(tmp_path, server, zone, site_cloudflare_account_id="acc-named",
        site_analytics={"umami": False, "cloudflare_web_analytics": True})
    paths = [r.path for r in server.requests]
    assert ("/accounts/acc-named/rum/site_info/list" in paths, "/zones/%s" % zone["id"] in paths) == (True, False)


def test_without_an_account_in_the_inventory_the_zones_account_is_asked(tmp_path, serve):
    cloudflare = FakeCloudflare()
    zone = lite_zone(cloudflare)
    server = serve(cloudflare)
    run(tmp_path, server, zone, site_analytics={"umami": False, "cloudflare_web_analytics": True})
    assert "/accounts/%s/rum/site_info/list" % DEFAULT_ACCOUNT in [r.path for r in server.requests]


def test_a_token_that_may_not_write_stops_the_role(tmp_path, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_forbidden = True
    zone = lite_zone(cloudflare)
    result = run(tmp_path, serve(cloudflare), zone, site_analytics={"umami": False, "cloudflare_web_analytics": True})
    assert (result.returncode != 0, "Account Settings" in result.stdout) == (True, True)
