import pytest

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.google import Refused, ServiceAccount, reason
from fakes.google import CONSOLE_SCOPE, VERIFY_SCOPE, FakeTokens, service_account


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


def test_token_names_the_scope_it_was_asked_for(tokens):
    account = ServiceAccount(service_account(tokens.uri), tokens.uri)
    assert account.token(VERIFY_SCOPE).startswith("tok|" + VERIFY_SCOPE)


def test_token_is_asked_for_once_per_scope(tokens):
    account = ServiceAccount(service_account(tokens.uri), tokens.uri)
    account.token(CONSOLE_SCOPE)
    account.token(CONSOLE_SCOPE)
    assert tokens.issued == [CONSOLE_SCOPE]


def test_refused_signature_is_a_refusal(tokens):
    tokens.refuses = True
    with pytest.raises(Refused):
        ServiceAccount(service_account(tokens.uri), tokens.uri).token(VERIFY_SCOPE)


def test_dead_token_endpoint_is_unreachable(tokens):
    uri = tokens.uri
    tokens.close()
    with pytest.raises(Unreachable):
        ServiceAccount(service_account(uri), uri).token(VERIFY_SCOPE)


def test_key_without_private_key_is_refused():
    with pytest.raises(ValueError):
        ServiceAccount('{"client_email": "leer@krot-units.iam.gserviceaccount.com"}')


def test_api_refusal_reads_the_message():
    assert reason({"error": {"code": 403, "message": "The caller does not have permission"}}) == \
        "The caller does not have permission"


def test_token_refusal_reads_code_and_description():
    assert reason({"error": "invalid_grant", "error_description": "Invalid JWT Signature."}) == \
        "invalid_grant: Invalid JWT Signature."


def test_token_endpoint_failing_on_its_side_is_unreachable(tokens):
    tokens.fails_with = 503
    with pytest.raises(Unreachable):
        ServiceAccount(service_account(tokens.uri), tokens.uri).token(VERIFY_SCOPE)
