from krot_index import night
from krot_index.night import Offer, Refused, Spending, share_of


def test_share_drops_the_remainder():
    assert share_of(200, 3) == 66


def test_share_never_falls_to_nothing():
    assert share_of(200, 300) == 1


def test_spent_day_is_green():
    assert not Offer({"unknown": 3}, attempted=3, refused=Refused("Quota exceeded", exhausted=True)).fails()


def test_pace_refusal_is_green():
    assert not Offer({"unknown": 3}, attempted=3, refused=Refused("ThrottleHost", too_fast=True)).fails()


def test_ownership_refusal_is_red():
    assert Offer({"unknown": 3}, attempted=3, refused=Refused("no owner", ownership=True)).fails()


def test_nothing_taken_without_a_reason_is_red():
    assert Offer({"unknown": 3}, attempted=3).fails()


def test_nothing_due_is_green():
    assert not Offer({"unknown": 3}, held=3).fails()


def test_empty_site_is_green():
    assert not Offer({}).fails()


def test_engine_that_answered_about_nothing_is_red():
    assert Offer({night.UNASKED: 4}).fails()


def test_engine_that_was_only_throttled_is_green():
    assert not Offer({night.THROTTLED: 4}).fails()


def test_unreadable_site_is_red():
    assert Offer.unreadable().fails()


def test_unreadable_site_reports_no_queue():
    row = Spending("rufnummer.de", "google", Offer.unreadable(), 66, True)
    assert (row.held, row.waiting, row.refusal) == (None, None, "unreadable")


def test_named_allowance_is_stored_as_allowance():
    row = Spending("rufnummer.de", "bing", Offer({"unknown": 1}), 22, True)
    assert (row.allowance, row.floor) == (22, None)


def test_guessed_allowance_is_stored_as_floor():
    row = Spending("rufnummer.de", "bing", Offer({"unknown": 1}), 10, False)
    assert (row.allowance, row.floor) == (None, 10)


def test_unrecognised_refusal_is_filed_for_a_person():
    assert night.refusal_of(Offer({"unknown": 1}, refused=Refused("something new"))) == "ownership"
