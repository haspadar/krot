"""Two rule sets, each shaped like a real project's: one with cards, places and a bare
segment; one with numbers and codes and no bare segment.

The first one's answers were checked against the earlier implementation on 40
thousand paths before this program replaced it (openspec change
collect-crawler-visits); these are one path per rule, to say which rule broke.
"""

import pytest

from krot_collect.sections import Sections

CARDS = Sections(
    rules=[{"section": "profile", "prefixes": ["/profil/", "/anketa/"], "bare": "other"},
           {"section": "listing", "prefixes": ["/bezirke/", "/orte/"], "bare": "self"}],
    bare_segment="listing",
    service_words=["agb", "datenschutz"],
    slice={"segments": 3, "last": r"\d{2}-\d{2}", "section": "listing"},
    media_prefix="/media/",
)

NUMBERS = Sections(
    rules=[{"section": "number", "prefixes": ["/nummer/"], "bare": "other"},
           {"section": "code", "prefixes": ["/vorwahl/"], "bare": "self"}],
)


@pytest.mark.parametrize("path, section", [
    ("", "home"),
    ("/", "home"),
    ("/?utm=1", "home"),
    ("/robots.txt", "robots"),
    ("/sitemap.xml", "sitemap"),
    ("/sitemap-3f9a2c.xml", "sitemap"),
    ("/media/x.jpg", "media"),
    ("/profil/anna", "profile"),
    ("/profil/", "other"),
    ("/profil", "other"),
    ("/bezirke/mitte", "listing"),
    ("/orte", "listing"),
    ("/orte/", "listing"),
    ("/berlin", "listing"),
    ("/berlin?page=2", "listing"),
    ("/agb", "other"),
    ("/AGB", "other"),
    ("/favicon.ico", "other"),
    ("/FAVICON.ICO", "listing"),
    ("/uralsk/parni/25-30", "listing"),
    ("/uralsk/parni/25-300", "other"),
    ("/a/b", "other"),
    ("/.env", "listing"),
])
def test_cards_and_places(path, section):
    assert CARDS.of(path) == section


def test_a_tailed_prefix_of_a_later_rule_wins_over_a_bare_prefix_of_an_earlier_one():
    # `/ab` is the first rule's bare prefix and the second rule's prefix with a
    # tail; rule by rule it would be `first`.
    rules = Sections(rules=[{"section": "first", "prefixes": ["/ab/"], "bare": "self"},
                            {"section": "second", "prefixes": ["/a"], "bare": "self"}])
    assert rules.of("/ab") == "second"


@pytest.mark.parametrize("path, section", [
    ("/nummer/0301234567", "number"),
    ("/nummer/", "other"),
    ("/vorwahl/030", "code"),
    ("/vorwahl", "code"),
    ("/impressum", "other"),
    ("/suche", "other"),
    ("/sitemap-5a1b.xml", "sitemap"),
    ("/media/x.jpg", "other"),
])
def test_numbers_and_codes(path, section):
    assert NUMBERS.of(path) == section
