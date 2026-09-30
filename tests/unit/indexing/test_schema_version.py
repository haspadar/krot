"""The schema's version is written in three places, and they must agree.

The role applies schema.sql only when the database is not at the version it
names, and the program refuses any version but its own. Raised in one place
alone, the role would never reapply the file, or every night would go red over a
schema that is fine.
"""

import os
import re

import yaml

from krot_index import store

ROLE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "roles", "indexing")


def test_role_applies_the_version_the_program_expects():
    with open(os.path.join(ROLE, "vars", "main.yml")) as source:
        assert yaml.safe_load(source)["indexing_schema_version"] == store.SCHEMA_VERSION


def test_schema_file_writes_the_version_the_program_expects():
    with open(os.path.join(ROLE, "files", "schema.sql")) as source:
        written = re.findall(r"INSERT INTO krot_index\.schema_version \(version\) VALUES \((\d+)\)", source.read())
    assert written == [str(store.SCHEMA_VERSION)]
