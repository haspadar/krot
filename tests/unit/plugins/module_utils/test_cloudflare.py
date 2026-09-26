from ansible_collections.haspadar.krot.plugins.module_utils.cloudflare import comparable, sendable


def test_number_setting_is_sent_as_a_number():
    assert sendable("0") == 0


def test_negative_number_setting_is_sent_as_a_number():
    assert sendable(-1) == -1


def test_word_setting_is_sent_as_a_word():
    assert sendable("strict") == "strict"


def test_boolean_compares_as_on_off():
    assert comparable(True) == "on"


def test_number_and_its_text_compare_equal():
    assert comparable(0) == comparable("0")
