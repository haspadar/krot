from datetime import date

from krot_collect import logline
from krot_collect.agents import Agents
from krot_collect.ranges import from_rows
from krot_collect.sections import Pair, Sections
from krot_collect.tally import Tally

DAY = date(2026, 8, 22)
GOOGLE = "Mozilla/5.0 (compatible; Googlebot/2.1)"
READER = "ChatGPT-User/1.0"
TRAINER = "GPTBot/1.1"
PERSON = "Mozilla/5.0 (Windows NT 10.0) Chrome/120"
RANGES = [("googlebot", "66.249.64.0/19")]


def line(path="/", status=200, agent=GOOGLE, address="66.249.66.1", size=100, tail=" cf=DE rt=0.100", day="22"):
    return '[%s/Aug/2026:10:00:00 +0300] %s - a.example "GET %s HTTP/1.1" %d %d "-" "%s"%s' % (
        day, address, path, status, size, agent, tail)


def tally(lines, ai_paths=False, ranges=RANGES):
    sections = Sections(rules=[{"section": "card", "prefixes": ["/card/"], "bare": "other"}], media_prefix="/media/")
    return Tally(Agents(), from_rows(ranges), sections, logline.FORMATS["time_first"], ai_paths).of(lines)


def test_a_day_of_people_alone_is_still_a_day_read():
    assert tally([line(agent=PERSON)]).days == {DAY}


def test_a_person_is_counted_as_human_and_not_as_a_crawler():
    reading = tally([line(agent=PERSON)])
    assert (reading.requests[DAY]["human"], reading.crawlers) == (1, {})


def test_crawlers_plus_people_are_every_request():
    reading = tally([line(), line(agent=PERSON), line(agent=READER, address="1.1.1.1"), line(path="/.env",
                                                                                             agent=TRAINER)])
    assert sum(one[0] for one in reading.crawlers.values()) + reading.requests[DAY]["human"] \
        == reading.requests[DAY]["requests"]


def test_the_sections_of_a_family_sum_to_its_requests():
    reading = tally([line(path="/card/1"), line(path="/x"), line(status=404), line(path="/media/a.jpg")])
    for (day, family), figures in reading.crawlers.items():
        assert sum(count for (d, f, _, _), count in reading.sections.items() if (d, f) == (day, family)) == figures[0]


def test_an_address_outside_the_published_ranges_is_unverified():
    assert (DAY, "googlebot-unverified") in tally([line(address="203.0.113.9")]).crawlers


def test_a_family_that_publishes_no_ranges_is_not_unverified():
    assert (DAY, "googlebot") in tally([line(address="203.0.113.9")], ranges=[]).crawlers


def test_a_claimed_ai_crawler_asking_for_credentials_is_an_impostor():
    assert (DAY, "impostor") in tally([line(path="/.env", agent=TRAINER)]).crawlers


def test_googlebot_asking_for_credentials_stays_googlebot():
    assert (DAY, "googlebot") in tally([line(path="/.env")]).crawlers


def test_a_photograph_is_counted_apart():
    assert (DAY, "googlebot-media") in tally([line(path="/media/a.jpg")]).crawlers


def test_an_unverified_photograph_is_not_also_media():
    assert (DAY, "googlebot-unverified") in tally([line(path="/media/a.jpg", address="203.0.113.9")]).crawlers


def test_without_a_media_prefix_nothing_is_media():
    sections = Sections()
    reading = Tally(Agents(), from_rows(RANGES), sections, logline.FORMATS["time_first"]).of([line(path="/media/a")])
    assert (DAY, "googlebot") in reading.crawlers


def test_errors_are_statuses_of_400_and_above():
    assert tally([line(status=404), line(status=301)]).crawlers[(DAY, "googlebot")][2] == 1


def test_a_line_without_rt_is_not_a_zero_reading():
    assert tally([line(tail=""), line()]).requests[DAY]["rt_count"] == 1


def test_exactly_one_second_is_not_slow():
    assert tally([line(tail=" rt=1.000"), line(tail=" rt=1.001")]).requests[DAY]["slow"] == 1


def test_a_500_on_robots_is_counted_as_robots():
    assert tally([line(path="/robots.txt?v=2", status=503)]).requests[DAY]["robots_5xx"] == 1


def test_a_404_on_robots_is_not_an_outage():
    assert tally([line(path="/robots.txt", status=404)]).requests[DAY]["robots_5xx"] == 0


def test_paths_are_kept_only_when_the_project_asks():
    assert tally([line(agent=READER, address="1.1.1.1")]).paths == {}


def test_a_readers_path_is_kept_without_its_query():
    reading = tally([line(path="/card/7?utm=x", agent=READER)], ai_paths=True)
    assert reading.paths == {(DAY, "chatgpt-user", "/card/7"): 1}


def test_a_trainers_path_is_not_kept():
    assert tally([line(agent=TRAINER)], ai_paths=True).paths == {}


def test_a_long_path_is_cut_to_255_bytes():
    reading = tally([line(path="/" + "a" * 400, agent=READER)], ai_paths=True)
    assert [len(path) for (_, _, path) in reading.paths] == [255]


def test_without_drops_a_spoiled_day_whole():
    reading = tally([line(day="21"), line(day="22")]).without({DAY})
    assert (reading.days, set(reading.requests), {day for day, _ in reading.crawlers}) \
        == ({date(2026, 8, 21)}, {date(2026, 8, 21)}, {date(2026, 8, 21)})


def test_a_pair_applies_to_the_domain_that_declared_it_and_not_to_another():
    mine = Tally(Agents(), from_rows(RANGES), Sections(), logline.FORMATS["time_first"],
                 pairs={"a.example": Pair("listing")})
    where = {domain: [key[2] for key in mine.of([line(path="/france/paris")], domain).sections]
             for domain in ("a.example", "b.example")}
    assert where == {"a.example": ["listing"], "b.example": ["other"]}
