"""The local pre-merge command: what it runs for a scenario, and what it refuses.

The molecule calls themselves are not run here — that is what the command is
for. What can go wrong in the command is the choice: a name that is not a
scenario must stop the run, and the short sequence must never quietly grow into
nothing or lose the verify step that reads the machine back.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "molecule_fast", ROOT / "scripts" / "molecule-fast.py"
)
fast = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fast)


def verbs(commands):
    return [command[1] for command in commands]


def test_the_default_sequence_starts_and_ends_with_nothing_left_over():
    assert verbs(fast.sequence("php", full=False, keep=False)) == [
        "destroy", "converge", "idempotence", "verify", "destroy",
    ]


def test_the_default_sequence_reads_the_machine_back():
    assert "verify" in verbs(fast.sequence("php", full=False, keep=False))


def test_keeping_the_container_skips_both_destroys():
    assert verbs(fast.sequence("php", full=False, keep=True)) == [
        "converge", "idempotence", "verify",
    ]


def test_quick_drops_only_the_idempotence_pass():
    assert verbs(fast.sequence("php", full=False, keep=False, idempotence=False)) == [
        "destroy", "converge", "verify", "destroy",
    ]


def test_the_full_cycle_is_molecule_test_for_that_scenario_only():
    assert fast.sequence("php", full=True, keep=False) == [["molecule", "test", "-s", "php"]]


def test_every_command_names_its_scenario():
    commands = fast.sequence("nginx", full=False, keep=False)
    assert all(command[-2:] == ["-s", "nginx"] for command in commands)


def test_a_name_that_is_not_a_scenario_stops_the_run():
    with pytest.raises(SystemExit, match="unknown scenario: nope"):
        fast.choose("", ["php", "nope"])


def test_named_scenarios_are_taken_as_given():
    assert fast.choose("", ["php", "nginx"]) == ["php", "nginx"]


def test_without_names_the_selector_decides():
    listing = json.dumps({"full": False, "scenarios": ["fail2ban"], "empty": False})
    assert fast.choose(listing, []) == ["fail2ban"]


def test_the_real_tree_has_scenarios_to_choose_from():
    assert "php" in fast.scenarios_on_disk()
