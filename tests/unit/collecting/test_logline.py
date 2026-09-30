from datetime import date

from krot_collect import logline

TIME_FIRST = logline.FORMATS["time_first"]
LINE = ('[22/Aug/2026:00:39:03 +0300] 203.0.113.9 - a.example "GET /card/7?x=1 HTTP/2.0" 200 5120 "-" '
        '"Mozilla/5.0 (compatible; Googlebot/2.1)" cf=DE rt=0.042')


def read(text):
    return logline.read(text, TIME_FIRST)


def test_the_address_is_the_address_despite_the_space_inside_the_time():
    assert read(LINE).address == "203.0.113.9"


def test_the_day_is_the_one_the_machine_wrote_not_the_utc_one():
    assert read(LINE).day == date(2026, 8, 22)


def test_the_path_is_the_request_without_method_and_protocol():
    assert read(LINE).path == "/card/7?x=1"


def test_the_response_time_is_read():
    assert read(LINE).response_time == 0.042


def test_a_zero_response_time_is_zero():
    assert read(LINE.replace("rt=0.042", "rt=0.000")).response_time == 0.0


def test_a_line_ending_at_the_agent_has_no_response_time_rather_than_zero():
    assert read(LINE.split(" cf=")[0]).response_time is None


def test_an_empty_rt_field_is_no_reading():
    assert read(LINE.replace("rt=0.042", "rt=")).response_time is None


def test_a_request_without_spaces_is_its_own_path():
    assert read(LINE.replace("GET /card/7?x=1 HTTP/2.0", "\\x16\\x03")).path == "\\x16\\x03"


def test_a_half_written_line_is_not_a_line():
    assert read(LINE[:40]) is None


def test_a_day_that_does_not_exist_is_not_a_line():
    assert read(LINE.replace("22/Aug", "31/Sep")) is None


def test_a_lowercase_month_is_read():
    assert read(LINE.replace("Aug", "aug")).day == date(2026, 8, 22)


def test_the_agent_is_unquoted():
    assert read(LINE).agent == "Mozilla/5.0 (compatible; Googlebot/2.1)"
