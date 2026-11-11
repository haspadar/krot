"""Run the role's actual preflight and env template without touching a server."""

import copy
import os
import re
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
ROLE = ROOT / "roles/indexing"
SITE = {"domain": "archive.test", "sitemap_url": "https://archive.test/s.xml", "yandex_account": "archive"}
PROJECT = {"database": "library", "reader": "reader", "engines": ["yandex"],
           "yandex_accounts": {"archive": "archive-token"}, "sites": [SITE]}


def preflight(tmp_path, project, more=None, render=False):
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    tasks = tasks[:next(i for i, task in enumerate(tasks) if task["name"] == "Offer each project's pages")]
    variables = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    variables.update(yaml.safe_load((ROLE / "vars/main.yml").read_text()))
    variables["indexing_projects"] = {"library": project, **(more or {})}
    if render:
        variables.update(ansible_managed="test", indexing_plan={"name": "library", "engines": ["yandex"]})
        tasks.append({"name": "Render the private environment", "ansible.builtin.copy": {
            "content": "{{ lookup('ansible.builtin.template', '" + str(ROLE / "templates/project.env.j2") + "') }}",
            "dest": str(tmp_path / "project.env"), "mode": "0600"}})
    play = [{"hosts": "localhost", "gather_facts": False, "vars": variables, "tasks": tasks}]
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump(play))
    return subprocess.run([sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", "-c", "local", str(path)],
                          cwd=ROOT, env={**os.environ, "ANSIBLE_NOCOLOR": "1"}, capture_output=True, text=True)


@pytest.mark.parametrize("accounts,account,engines,default,failed", [
    ({"archive": "archive-token"}, "archive", ["yandex"], None, None),
    ({"archive": "archive-token"}, "archive", ["yandex"], "main-token", None),
    ({}, None, ["yandex"], "main-token", None),
    ([], "archive", ["yandex"], "main-token", "Assert each project's Yandex accounts are named"),
    ({"Bad-name": "archive-token"}, "Bad-name", ["yandex"], "main-token", "Assert each project's Yandex accounts are named"),
    ({1: "archive-token"}, 1, ["yandex"], "main-token", "Assert each project's Yandex accounts are named"),
    ({"archive": "archive-token"}, "absent", ["yandex"], "main-token", "Assert each site names a Yandex account"),
    ({"archive": "archive-token"}, "archive", ["bing"], "main-token", "Assert each project's Yandex accounts are named"),
    ({"archive": "archive-token"}, None, ["yandex"], "main-token", "Assert every Yandex account is used"),
    ({"archive": ""}, "archive", ["yandex"], None, "Assert every Yandex account's key"),
    ({"archive": None}, "archive", ["yandex"], None, "Assert every Yandex account's key"),
    ({"archive": True}, "archive", ["yandex"], None, "Assert every Yandex account's key"),
    ({"archive": 7}, "archive", ["yandex"], None, "Assert every Yandex account's key"),
    ({"archive": "line\nbreak"}, "archive", ["yandex"], None, "Assert every Yandex account's key"),
    ({"archive": "same-token"}, "archive", ["yandex"], "same-token", "Assert no two projects share a key"),
    ({"archive": "same-token", "backup": "same-token"}, "archive", ["yandex"], None, "Assert every Yandex account is used"),
    ({}, None, ["yandex"], None, "Assert every declared engine has its key"),
])
def test_yandex_inventory_is_validated_before_server_changes(tmp_path, accounts, account, engines, default, failed):
    project = copy.deepcopy(PROJECT)
    project.update(yandex_accounts=accounts, engines=engines, bing_key="bing-key")
    if account is None:
        project["sites"][0].pop("yandex_account")
    else:
        project["sites"][0]["yandex_account"] = account
    if default is not None:
        project["yandex_token"] = default
    result = preflight(tmp_path, project)
    assert (result.returncode == 0 if failed is None else result.returncode != 0 and re.findall(r"TASK \[(.*?)\]", result.stdout)[-1].startswith(failed)), result.stdout + result.stderr


def test_site_not_offered_to_yandex_cannot_name_its_account(tmp_path):
    project = copy.deepcopy(PROJECT)
    project.update(engines=["yandex", "bing"], bing_key="bing-key", yandex_token="main-token")  # secret-lint: allow — fake tokens
    project["sites"].append({"domain": "main.test", "sitemap_url": "https://main.test/s.xml"})
    project["sites"][0]["engines"] = ["bing"]
    result = preflight(tmp_path, project)
    assert result.returncode != 0 and re.findall(r"TASK \[(.*?)\]", result.stdout)[-1].startswith("Assert each site names a Yandex account"), result.stdout + result.stderr


def test_two_projects_cannot_share_an_account_token(tmp_path):
    result = preflight(tmp_path, copy.deepcopy(PROJECT), {"other": copy.deepcopy(PROJECT)})
    assert result.returncode != 0 and re.findall(r"TASK \[(.*?)\]", result.stdout)[-1].startswith("Assert no two projects share a key"), result.stdout + result.stderr


@pytest.mark.parametrize("default", [None, "main-token"])
def test_env_template_delivers_named_tokens_and_keeps_default_optional(tmp_path, default):
    project = copy.deepcopy(PROJECT)
    if default:
        project["yandex_token"] = default
    result = preflight(tmp_path, project, render=True)
    assert result.returncode == 0 and [line for line in (tmp_path / "project.env").read_text().splitlines() if line and not line.startswith("#")] == (
        (["KROT_INDEX_YANDEX_TOKEN=main-token"] if default else []) + ["KROT_INDEX_YANDEX_TOKEN_ARCHIVE=archive-token"]  # secret-lint: allow — fake tokens
    ), result.stdout + result.stderr


def test_two_named_accounts_cannot_share_a_token(tmp_path):
    project = copy.deepcopy(PROJECT)
    project["yandex_accounts"]["backup"] = "archive-token"
    project["sites"].append({"domain": "backup.test", "sitemap_url": "https://backup.test/s.xml", "yandex_account": "backup"})
    result = preflight(tmp_path, project)
    assert result.returncode != 0 and re.findall(r"TASK \[(.*?)\]", result.stdout)[-1].startswith("Assert no two projects share a key"), result.stdout + result.stderr
