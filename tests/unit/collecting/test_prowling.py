import pytest

from krot_collect.prowling import is_prowling


@pytest.mark.parametrize("path", [
    "/.env",
    "/root/.aws/credentials",
    "/wp-admin/setup.php",
    "/static/..;/.env",
    "/%2e%2e/etc/passwd",
    "/..%b9",
    "/latest/meta-data?target=169.254.169.254",
    "/server.key",
])
def test_a_scan(path):
    assert is_prowling(path)


@pytest.mark.parametrize("path", [
    "/profil/tom.key-berlin",
    "/profil/lisa..anna",
    "/bezirke/credentials-mitte",
    "/berlin",
])
def test_a_page(path):
    assert not is_prowling(path)
