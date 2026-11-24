"""What site_preflight asks of its modules, read from the role itself.

A module test proves what a flag does; whether the role passes it is a line no scenario fails
without: molecule's fake keeps every API on for every key.
"""

import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TASKS = os.path.join(ROOT, "roles", "site_preflight", "tasks", "main.yml")


def tasks(listed):
    for task in listed:
        yield task
        for nested in ("block", "rescue", "always"):
            yield from tasks(task.get(nested, []))


def calls_of(module):
    with open(TASKS) as handle:
        return [task[module] for task in tasks(yaml.safe_load(handle)) if module in task]


# Without verify, gsc_site asks Site Verification only, and a launching key whose project has
# the Search Console API off passes the check and fails the launch after its deploy.
def test_google_is_checked_with_verify_so_search_console_answers_the_launching_key():
    assert [call.get("verify") for call in calls_of("haspadar.krot.gsc_site")] == [True]


# The Web Analytics question must stay a question: written outside check mode it would turn the
# record on in the report that is meant to change nothing, for a launch that was only asked about.
def test_web_analytics_is_asked_only_inside_the_block_that_writes_nothing():
    with open(TASKS) as handle:
        blocks = [task for task in yaml.safe_load(handle) if "block" in task and task.get("check_mode") is True]
    asked = [t for b in blocks for t in b["block"] if "haspadar.krot.cloudflare_web_analytics" in t]
    assert len(asked) == 1 and calls_of("haspadar.krot.cloudflare_web_analytics") == [asked[0]["haspadar.krot.cloudflare_web_analytics"]]


def test_web_analytics_is_asked_only_when_the_switch_is_on():
    (task,) = [t for t in tasks(yaml.safe_load(open(TASKS))) if "haspadar.krot.cloudflare_web_analytics" in t]
    assert "site_analytics.cloudflare_web_analytics | default(false)" in task["when"]
