from krot_collect.agents import OTHER, Agents

MONITOR = [{"mark": "watchdog-probe", "family": "monitor"}]


def test_the_image_crawler_is_not_filed_as_the_page_crawler():
    assert Agents().family("Googlebot-Image/1.0") == "googlebot-image"


def test_the_mark_is_found_inside_the_line_not_at_its_front():
    assert Agents().family("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X) (compatible; Googlebot/2.1)") == "googlebot"


def test_a_line_carrying_a_reader_and_a_trainer_mark_is_the_reader():
    assert Agents().family("Claude-User/1.0; +claudebot@anthropic.com") == "claude-user"


def test_a_synonym_names_its_family():
    assert Agents().family("anthropic-ai") == "claudebot"


def test_a_browser_is_a_person_not_other():
    assert Agents().family("Mozilla/5.0 (Windows NT 10.0) Chrome/120") is None


def test_an_unnamed_robot_is_other():
    assert Agents().family("python-requests/2.31") == OTHER


def test_the_projects_mark_comes_before_the_shared_words():
    assert Agents(MONITOR).family("watchdog-probe bot/1") == "monitor"


def test_without_the_projects_mark_its_monitor_is_other():
    assert Agents().family("watchdog-probe bot/1") == OTHER


def test_a_reader_keeps_its_paths():
    assert Agents().reads_for_ai("chatgpt-user")


def test_a_trainer_does_not_keep_its_paths():
    assert not Agents().reads_for_ai("gptbot")


def test_a_suffixed_reader_does_not_keep_its_paths():
    assert not Agents().reads_for_ai("chatgpt-user-unverified")


def test_a_trainer_can_be_impersonated():
    assert Agents().is_impersonated("claudebot")


def test_googlebot_is_not_in_the_impersonated_lists():
    assert not Agents().is_impersonated("googlebot")


def test_a_projects_reader_is_a_reader():
    assert Agents([{"mark": "newreader", "family": "newreader", "ai": "read"}]).reads_for_ai("newreader")


def test_the_dictionary_orders_every_longer_mark_before_a_shorter_one_it_contains():
    marks = [mark for mark, _ in Agents().marks]
    for later, longer in enumerate(marks):
        for shorter in marks[:later]:
            assert shorter not in longer or shorter == longer, "%s shadows %s" % (shorter, longer)
