"""Which scenarios a change reaches — on small trees built here, and on the real one.

The small trees pin one rule each. The last tests read this repository itself:
they are what keeps the selector honest as roles and scenarios are added, since
a role that quietly stops selecting its own scenario would make CI green by
running nothing.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "molecule_select", ROOT / "scripts" / "molecule-select.py"
)
select_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(select_module)


def write(root, relative, text="---\n"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path):
    """Four roles: alpha and beta stand alone, gamma runs alpha, delta reads
    beta's variable. One scenario each for alpha, beta and gamma; a fourth
    scenario runs a playbook that runs delta."""
    for role in ("alpha", "beta", "gamma", "delta", "lonely"):
        write(tmp_path, f"roles/{role}/tasks/main.yml")
    write(tmp_path, "roles/beta/defaults/main.yml", "---\nbeta_port: 22\n")
    write(
        tmp_path,
        "roles/gamma/tasks/main.yml",
        "- ansible.builtin.include_role:\n    name: haspadar.krot.alpha\n",
    )
    write(
        tmp_path,
        "roles/delta/tasks/main.yml",
        "- ansible.builtin.debug:\n    msg: '{{ beta_port | default(22) }}'\n"
        "- haspadar.krot.fancy_module:\n",
    )
    for scenario in ("alpha", "beta", "gamma"):
        write(tmp_path, f"molecule/{scenario}/molecule.yml")
    write(
        tmp_path,
        "molecule/gamma/converge.yml",
        "- hosts: all\n  roles:\n    - role: gamma\n",
    )
    write(tmp_path, "molecule/launch/molecule.yml")
    write(
        tmp_path,
        "molecule/launch/converge.yml",
        "- ansible.builtin.import_playbook: haspadar.krot.launch\n"
        "# serves tests/fakes\n",
    )
    write(
        tmp_path,
        "playbooks/launch.yml",
        "- hosts: all\n  tasks:\n    - ansible.builtin.include_role:\n"
        "        name: haspadar.krot.delta\n",
    )
    return select_module.Tree(tmp_path)


def chosen(tree, *paths):
    return select_module.select(tree, list(paths))


def test_documentation_alone_needs_no_scenario(repo):
    result = chosen(repo, "wiki/README.md", "openspec/changes/x/tasks.md", "README.md")
    assert (result["empty"], result["full"], result["scenarios"]) == (True, False, [])


def test_a_role_selects_its_own_scenario_and_nothing_else(repo):
    assert chosen(repo, "roles/gamma/tasks/main.yml")["scenarios"] == ["gamma"]


def test_a_role_selects_the_scenarios_of_roles_that_run_it(repo):
    assert chosen(repo, "roles/alpha/tasks/main.yml")["scenarios"] == ["alpha", "gamma"]


def test_a_role_whose_variable_another_reads_selects_its_reader(repo):
    # delta reads beta_port, and the playbook runs delta: no include shows it
    assert chosen(repo, "roles/beta/defaults/main.yml")["scenarios"] == ["beta", "launch"]


def test_a_role_nothing_exercises_selects_nothing_but_is_not_a_full_run(repo):
    result = chosen(repo, "roles/lonely/tasks/main.yml")
    assert (result["scenarios"], result["empty"], result["full"]) == ([], True, False)


def test_a_scenario_directory_selects_that_scenario(repo):
    assert chosen(repo, "molecule/gamma/verify.yml")["scenarios"] == ["gamma"]


def test_a_playbook_selects_the_scenario_that_imports_it(repo):
    assert chosen(repo, "playbooks/launch.yml")["scenarios"] == ["launch"]


def test_a_module_selects_the_scenarios_whose_roles_call_it(repo):
    assert chosen(repo, "plugins/modules/fancy_module.py")["scenarios"] == ["launch"]


def test_fakes_select_the_scenario_that_serves_them(repo):
    assert chosen(repo, "tests/fakes/server.py")["scenarios"] == ["launch"]


def test_a_removed_role_still_selects_the_scenario_that_ran_it(repo):
    write(
        repo.root,
        "molecule/gamma/converge.yml",
        "- hosts: all\n  roles:\n    - role: gone\n",
    )
    tree = select_module.Tree(repo.root)
    assert chosen(tree, "roles/gone/tasks/main.yml")["scenarios"] == ["gamma"]


@pytest.mark.parametrize(
    "path",
    [
        "galaxy.yml",
        "requirements.yml",
        "molecule/requirements.yml",
        ".github/workflows/lint.yml",
        "plugins/module_utils/api.py",
        "scripts/molecule-select.py",
        "roles/stray-file.yml",
        "something/nobody/named.txt",
    ],
)
def test_shared_or_unnamed_paths_run_everything(repo, path):
    result = chosen(repo, path)
    assert (result["full"], result["scenarios"]) == (True, repo.scenarios)


def test_one_shared_path_among_documentation_still_runs_everything(repo):
    assert chosen(repo, "wiki/README.md", "galaxy.yml")["full"] is True


def test_every_scenario_is_run_by_a_change_to_its_own_directory():
    tree = select_module.Tree(ROOT)
    assert tree.scenarios, "the real tree has no scenarios"
    for scenario in tree.scenarios:
        result = select_module.select(tree, [f"molecule/{scenario}/molecule.yml"])
        assert scenario in result["scenarios"], scenario


def test_every_role_with_a_scenario_of_its_name_selects_it():
    tree = select_module.Tree(ROOT)
    named = [s for s in tree.scenarios if s in tree.roles]
    assert named, "no scenario carries the name of a role"
    for role in named:
        result = select_module.select(tree, [f"roles/{role}/tasks/main.yml"])
        assert role in result["scenarios"], role
