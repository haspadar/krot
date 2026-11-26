from copy import deepcopy

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.haspadar.krot.plugins.filter.google_analytics_passport import valid_google_analytics


def assignment(**changes):
    return dict(account_id="301144", property_id="550407450", stream_id="993201", measurement_id="G-EXAMPLE123",
                owner="operator@example.de", timezone="Europe/Berlin", since="2026-11-27") | changes


def test_absent_assignment_is_supported():
    assert valid_google_analytics(None) is True


def test_verified_assignment_is_accepted_without_changes():
    value = assignment()
    before = deepcopy(value)
    valid_google_analytics(value)
    assert value == before


@pytest.mark.parametrize("value", [False, "", [], {}, {"account_id": "301144"}])
def test_wrong_object_shape_is_refused(value):
    with pytest.raises(AnsibleFilterError):
        valid_google_analytics(value)


@pytest.mark.parametrize("field", ["account_id", "property_id", "stream_id", "measurement_id", "owner", "timezone", "since"])
@pytest.mark.parametrize("value", [None, 1, False, []])
def test_every_field_must_remain_a_string(field, value):
    with pytest.raises(AnsibleFilterError, match="must be a string"):
        valid_google_analytics(assignment(**{field: value}))


@pytest.mark.parametrize("field,value", [("account_id", "accounts/301144"), ("property_id", "550407450\n"),
                                        ("stream_id", ""), ("measurement_id", "G-bad"),
                                        ("measurement_id", "G-EXAMPLE123\n"), ("owner", ""),
                                        ("owner", "operator@example.de\n"), ("owner", "..@example.de"),
                                        ("owner", "user@host..de"), ("owner", "user@-host.de"),
                                        ("owner", "reader@cloud.iam.gserviceaccount.com"),
                                        ("timezone", "Europe/Unknown"), ("timezone", "../etc/passwd"), ("timezone", "localtime"), ("timezone", "posix/Europe/Berlin"),
                                        ("since", "2026-02-30"), ("since", "20261127"),
                                        ("since", "2026-W48-5"), ("since", "2026-11-27\n")])
def test_invalid_assignment_values_are_refused(field, value):
    with pytest.raises(AnsibleFilterError):
        valid_google_analytics(assignment(**{field: value}))


def test_extra_credential_field_is_never_exported():
    with pytest.raises(AnsibleFilterError):
        valid_google_analytics(assignment(credential_file="reader.json"))


@pytest.mark.parametrize("timezone", ["Europe/Minsk", "UTC", "Etc/GMT-1"])
def test_existing_property_timezone_is_accepted(timezone):
    assert valid_google_analytics(assignment(timezone=timezone)) is True
