import io
from contextlib import nullcontext
from datetime import date, timedelta

import pytest

from krot_collect.gsc import Collection, planned_days
from krot_collect.gsc_api import GscError
from krot_collect.gsc_store import DATASETS


class MemoryStore:
    def __init__(self):
        self.saved = {}
        self.attempts = []
        self.dropped = None

    def exclusive(self):
        return nullcontext()

    def markers(self, site, property):
        return {(day, dataset) for (domain, day, dataset) in self.saved if domain == site}

    def horizon(self, site, property):
        known = [day for domain, day, _ in self.saved if domain == site]
        known += [attempt["day"] for attempt in self.attempts if attempt["site"] == site]
        return min(known, default=None)

    def start(self, site, property, day, dataset):
        self.attempts.append({'site': site, 'day': day, 'dataset': dataset, 'status': 'running'})
        return len(self.attempts) - 1

    def finish(self, attempt, status, error=''):
        self.attempts[attempt].update(status=status, error=error)

    def replace(self, site, property, day, dataset, figures, attempt):
        self.saved[(site, day, dataset)] = figures
        self.attempts[attempt]['status'] = 'success'

    def latest(self, site, property, dataset):
        return max((day for domain, day, report in self.saved if domain == site and report == dataset), default=None)

    def forget(self, sites, cutoff):
        self.dropped = (sites, cutoff)


class Engine:
    def __init__(self, unavailable=(), refused=None, boundaries=None):
        self.unavailable = set(unavailable)
        self.refused = refused
        self.boundaries = boundaries or {}
        self.asked = []
        self.probed = []

    def first_incomplete(self, property, start, end):
        boundary = self.boundaries.get(property)
        if isinstance(boundary, Exception):
            raise boundary
        return boundary

    def finalized_days(self, property, start, end):
        self.probed.append((property, start))
        return set() if start in self.unavailable else {start.isoformat()}

    def fetch(self, property, day, dataset):
        self.asked.append((property, day, dataset))
        if dataset == self.refused:
            raise GscError(403, 'forbidden')
        return []


def config(**settings):
    return {'sites': [{'domain': 'gardens.test'}], 'gsc': settings}


def test_initial_backfill_has_twenty_eight_complete_dates():
    plan = planned_days(set(), date(2026, 10, 2), {})
    assert (len(plan), plan[0][0], plan[-1][0]) == (28, date(2026, 9, 4), date(2026, 10, 1))


def test_a_hole_behind_the_overlap_is_scheduled():
    today = date(2026, 8, 30)
    markers = {(today - timedelta(days=i), dataset) for i in range(1, 31) for dataset in DATASETS}
    markers.remove((date(2026, 8, 12), 'page'))
    assert (date(2026, 8, 12), ['page']) in planned_days(markers, today, {})


def test_successful_empty_reports_have_markers():
    store = MemoryStore()
    Collection(Engine(), store, io.StringIO(), io.StringIO(), date(2026, 7, 5)).collect(
        config(), date(2026, 7, 1), date(2026, 7, 1))
    assert [attempt['status'] for attempt in store.attempts] == ['success'] * 3


def test_an_unavailable_date_has_no_success_markers():
    store = MemoryStore()
    Collection(Engine(unavailable=[date(2026, 9, 28)]), store, io.StringIO(), io.StringIO(), date(2026, 10, 1)).collect(
        config(), date(2026, 9, 28), date(2026, 9, 28))
    assert (store.saved, [attempt['status'] for attempt in store.attempts]) == ({}, ['unavailable'] * 3)


def test_a_failed_report_preserves_previous_figures():
    store = MemoryStore()
    store.saved[('gardens.test', date(2026, 8, 8), 'page')] = ['old measurement']
    Collection(Engine(refused='page'), store, io.StringIO(), io.StringIO(), date(2026, 8, 10)).collect(
        config(), date(2026, 8, 8), date(2026, 8, 8))
    assert store.saved[('gardens.test', date(2026, 8, 8), 'page')] == ['old measurement']


def test_other_reports_continue_after_one_is_refused():
    engine = Engine(refused='query')
    Collection(engine, MemoryStore(), io.StringIO(), io.StringIO(), date(2026, 6, 20)).collect(
        config(), date(2026, 6, 15), date(2026, 6, 15))
    assert [dataset for _, _, dataset in engine.asked] == ['query', 'page', 'page_query']


def test_a_site_without_finalized_history_reports_staleness():
    today = date(2026, 5, 30)
    engine = Engine(unavailable=[day for day, _ in planned_days(set(), today, {})])
    err = io.StringIO()
    result = Collection(engine, MemoryStore(), io.StringIO(), err, today).collect(config())
    assert (result, err.getvalue().count('finalized data stale')) == (1, 3)


@pytest.mark.parametrize('start,end', [(date(2026, 9, 30), date(2026, 10, 2)),
                                      (date(2026, 10, 1), date(2026, 9, 1)),
                                      (date(2024, 1, 1), date(2024, 1, 2))])
def test_unsafe_explicit_ranges_are_refused(start, end):
    with pytest.raises(ValueError):
        planned_days(set(), date(2026, 10, 2), {}, start, end)


def test_a_quiet_day_before_the_boundary_is_a_measured_zero():
    store = MemoryStore()
    engine = Engine(unavailable=[date(2026, 9, 10)], boundaries={'sc-domain:gardens.test': date(2026, 9, 30)})
    Collection(engine, store, io.StringIO(), io.StringIO(), date(2026, 10, 3)).collect(
        config(), date(2026, 9, 10), date(2026, 9, 10))
    assert [attempt['status'] for attempt in store.attempts] == ['success'] * 3


def test_a_day_from_the_boundary_on_is_unavailable_without_asking_reports():
    store = MemoryStore()
    engine = Engine(boundaries={'sc-domain:gardens.test': date(2026, 9, 30)})
    Collection(engine, store, io.StringIO(), io.StringIO(), date(2026, 10, 3)).collect(
        config(), date(2026, 9, 30), date(2026, 9, 30))
    assert ([attempt['status'] for attempt in store.attempts], engine.asked) == (['unavailable'] * 3, [])


def test_a_site_without_a_boundary_borrows_the_earliest_of_the_run():
    store = MemoryStore()
    engine = Engine(boundaries={'sc-domain:harbour.test': date(2026, 9, 30), 'sc-domain:meadow.test': date(2026, 9, 29)})
    sites = {'sites': [{'domain': 'harbour.test'}, {'domain': 'meadow.test'}, {'domain': 'pond.test'}], 'gsc': {}}
    Collection(engine, store, io.StringIO(), io.StringIO(), date(2026, 10, 3)).collect(
        sites, date(2026, 9, 29), date(2026, 9, 29))
    assert [attempt['status'] for attempt in store.attempts if attempt['site'] == 'pond.test'] == ['unavailable'] * 3


def test_a_borrowed_boundary_replaces_the_day_probe():
    engine = Engine(boundaries={'sc-domain:harbour.test': date(2026, 9, 30)})
    sites = {'sites': [{'domain': 'harbour.test'}, {'domain': 'pond.test'}], 'gsc': {}}
    Collection(engine, MemoryStore(), io.StringIO(), io.StringIO(), date(2026, 10, 3)).collect(
        sites, date(2026, 9, 20), date(2026, 9, 20))
    assert engine.probed == []


def test_a_refused_boundary_falls_back_to_the_day_probe():
    engine = Engine(boundaries={'sc-domain:gardens.test': GscError(403, 'forbidden'),
                                'sc-domain:harbour.test': date(2026, 9, 30)})
    sites = {'sites': [{'domain': 'gardens.test'}, {'domain': 'harbour.test'}], 'gsc': {}}
    Collection(engine, MemoryStore(), io.StringIO(), io.StringIO(), date(2026, 10, 3)).collect(
        sites, date(2026, 9, 20), date(2026, 9, 20))
    assert engine.probed == [('sc-domain:gardens.test', date(2026, 9, 20))]


def test_the_failed_first_backfill_day_remains_scheduled_after_the_window_moves():
    today = date(2026, 10, 3)
    markers = {(date(2026, 9, 5) + timedelta(days=i), dataset) for i in range(27) for dataset in DATASETS}
    plan = planned_days(markers, today, {}, horizon=date(2026, 9, 4))
    assert (date(2026, 9, 4), list(DATASETS)) in plan
