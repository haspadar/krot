"""The words krot must not show: the projects that consume it and their sites.

Shared by names-lint.py, which refuses them in the tree, and wiki-index.py, which
masks them in the index it builds out of the change archive. One list, so the two
cannot drift apart.

The words are compared by hash, so this file does not name what it forbids —
it would otherwise be the one place in the tree that still did. A word is any
run of [a-z0-9] after splitting camel case and lowercasing, which catches
`acc-<name>`, `<name>'s`, `<name>.de` and `<Name>Deploy` alike. A name glued to
another lowercase word (`<name>shared`) is not caught: splitting there would
need a dictionary. To forbid another word, add the sha256 of its lowercase
spelling below — `printf '%s' word | shasum -a 256`.
"""

from __future__ import annotations

import hashlib
import re

FORBIDDEN = {
    "47fa91115b212214dbd018f357ab5883424f82b3e6d3de1bc20f04b2b319aac2",
    "61e8809900baf42d0287463b31aef80a422b3a8959fd49496cd1f230e3739799",
    "1372c63b35ea72a55bc5afac621482ea61a41dea630ba19583412545d4197641",
    "5862369d4456977e94676b7376cd3de71cb3c3c891aae27f445e56e08e3c41ad",
    "fa10c03906f12c3ff779c33079afb15e52b14ade96804f35fb6025619b826774",
    "5448199fe71a15959b536279d873c729da5088b31098eee83173bbac06738297",
    "13ac368599ba03b93a72142138bdfd4610ec7896d2ab2f66e62541d24b7183e5",
    "eb5219a9a50bdb51760481c6c642523a78c3555812b600b9769bcdce17403a47",
    "6e5e1ccf88c88d70a81707c0d74c7bbed5cfa0dc47d3dbf31f5c6979d6127720",
    "9e898946dec8daa8916e363d99bd1bd22d188d3f59c53df00d8e1effa500e0cc",
    "8566db9ce3b9c7aaf81f1d2e7ad7df8e0588efd1431c29a927d9d6401700cec0",
}

MASK = "‹проект›"

WORD = re.compile(r"[a-z0-9]+")
TOKEN = re.compile(r"[A-Za-z0-9]+")
# ShopDeploy -> Shop Deploy, HTTPServer -> HTTP Server: a name inside an
# identifier is still a name.
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def is_forbidden(word: str) -> bool:
    return hashlib.sha256(word.lower().encode()).hexdigest() in FORBIDDEN


def forbidden(line: str) -> bool:
    return any(is_forbidden(word) for word in WORD.findall(CAMEL.sub(" ", line).lower()))


def masked(text: str) -> str:
    """The text with every forbidden word replaced, the rest as it was."""

    def mask_token(match: re.Match[str]) -> str:
        parts = CAMEL.split(match.group(0))
        return "".join(MASK if is_forbidden(part) else part for part in parts)

    return TOKEN.sub(mask_token, text)
