"""Whether a request is prowling rather than crawling.

Taken from what a live scan actually requested, not from a list of famous
exploits: every entry is one the earlier implementation had already seen, and all
are after the same thing — credentials somebody left in a file.
"""

import re
from urllib.parse import unquote

MARKS = (
    ".env",
    ".git",
    ".aws",
    ".ssh",
    "wp-admin",
    "wp-login",
    "wp-content",
    "phpmyadmin",
    "phpinfo",
    "terraform.tfstate",
    "sftp-config",
    "docker-compose",
    "config.json",
    "settings.py",
    "/graphql",
    "/actuator",
    "/.well-known/security",
    # Cloud metadata: link-local, answers only from inside a cloud instance, so a
    # request naming it from outside asks the site to fetch its own provider's
    # credentials for the caller.
    "169.254.169.254",
)

# Only an attack at the end of a path segment. Slugs are catalogue data: loose,
# `.key` matches a profile called `tom.key` and `credentials` a district slug —
# real pages, filed as an attack.
EXTENSIONS = tuple(re.compile(re.escape(one) + r"($|[/?#])") for one in (".pem", ".key", "id_rsa", "credentials"))

# Traversal as a whole segment, in the spellings a live scan used —
# `/static/..;/.env` among them. Unanchored, `..` matches `/profil/lisa..anna`.
TRAVERSAL = re.compile(r"(^|/)\.\.($|[/;?#])")


def is_prowling(path):
    # A byte that decodes to no character becomes `?`, as the earlier
    # implementation's lowercasing substituted it — so `/..%b9` still ends its
    # segment and still reads as traversal.
    lowered = unquote(path, errors="replace").replace("�", "?").lower()
    if any(mark in lowered for mark in MARKS):
        return True
    if any(extension.search(lowered) for extension in EXTENSIONS):
        return True
    return TRAVERSAL.search(lowered) is not None
