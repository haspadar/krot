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
