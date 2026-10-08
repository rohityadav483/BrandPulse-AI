"""Analysis job gating: jobs wait for a free slot, are never dropped, and never hang forever.

No database: `run_analysis` and the row-failing helpers are replaced with spies.
"""

import threading
import time
import uuid

import pytest

from app.pipeline import jobs


@pytest.fixture(autouse=True)
def _fresh_gates():
    jobs._gate = jobs._Gate()
    jobs._investigation_gate = jobs._Gate()
    yield
    assert jobs._gate.running == 0, "a job leaked its slot"
    assert jobs._investigation_gate.running == 0


class _Runner:
    """Replacement for `run_analysis`: records order and peak concurrency."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.started = []
        self.finished = []
        self.release = threading.Event()
        self.entered = threading.Semaphore(0)

    def __call__(self, analysis_id, settings):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.started.append(analysis_id)
        self.entered.release()
        assert self.release.wait(5), "test never released the runner"
        with self.lock:
            self.active -= 1
            self.finished.append(analysis_id)


def _start(settings, analysis_id, **kwargs):
    t = threading.Thread(
        target=jobs.start_analysis_job, args=(analysis_id, settings), kwargs=kwargs
    )
    t.start()
    return t


def test_second_job_waits_for_the_first_then_runs(monkeypatch, make_settings):
    runner = _Runner()
    monkeypatch.setattr(jobs, "run_analysis", runner)
    settings = make_settings(max_concurrent_analyses=1)
    a, b = uuid.uuid4(), uuid.uuid4()

    first = _start(settings, a)
    assert runner.entered.acquire(timeout=5)
    second = _start(settings, b)
    time.sleep(0.2)
    assert runner.started == [a]  # b is waiting, NOT dropped and NOT running

    runner.release.set()
    first.join(5)
    second.join(5)
    assert runner.started == [a, b] and runner.finished == [a, b]
    assert runner.peak == 1


def test_max_concurrent_analyses_setting_is_honored(monkeypatch, make_settings):
    runner = _Runner()
    monkeypatch.setattr(jobs, "run_analysis", runner)
    settings = make_settings(max_concurrent_analyses=2)
    ids = [uuid.uuid4() for _ in range(3)]

    threads = [_start(settings, i) for i in ids]
    assert runner.entered.acquire(timeout=5) and runner.entered.acquire(timeout=5)
    time.sleep(0.2)
    assert len(runner.started) == 2  # third waits for a slot
    runner.release.set()
    for t in threads:
        t.join(5)
    assert sorted(map(str, runner.finished)) == sorted(map(str, ids))
    assert runner.peak == 2


def test_job_that_cannot_get_a_slot_is_failed_not_left_queued(monkeypatch, make_settings):
    runner = _Runner()
    monkeypatch.setattr(jobs, "run_analysis", runner)
    failed = []
    monkeypatch.setattr(jobs, "_mark_failed", lambda aid, s, reason: failed.append((aid, reason)))
    settings = make_settings(max_concurrent_analyses=1)
    a, b = uuid.uuid4(), uuid.uuid4()

    first = _start(settings, a)
    assert runner.entered.acquire(timeout=5)
    jobs.start_analysis_job(b, settings, queue_wait_seconds=0.1)  # gives up quickly

    assert [x[0] for x in failed] == [b]
    assert "busy" in failed[0][1]
    assert runner.started == [a]  # b never ran
    runner.release.set()
    first.join(5)


def test_crash_releases_the_slot_and_fails_the_row(monkeypatch, make_settings):
    marked = []
    monkeypatch.setattr(jobs, "_mark_failed_any", lambda aid, s: marked.append(aid))

    def boom(analysis_id, settings):
        raise RuntimeError("pipeline blew up")

    monkeypatch.setattr(jobs, "run_analysis", boom)
    settings = make_settings(max_concurrent_analyses=1)
    a = uuid.uuid4()
    jobs.start_analysis_job(a, settings)
    assert marked == [a]
    assert jobs._gate.running == 0

    ran = []
    monkeypatch.setattr(jobs, "run_analysis", lambda aid, s: ran.append(aid))
    b = uuid.uuid4()
    jobs.start_analysis_job(b, settings)  # the next job is not blocked by the crash
    assert ran == [b]


def test_many_queued_jobs_all_run_one_at_a_time(monkeypatch, make_settings):
    runner = _Runner()
    runner.release.set()
    monkeypatch.setattr(jobs, "run_analysis", runner)
    settings = make_settings(max_concurrent_analyses=1)
    ids = [uuid.uuid4() for _ in range(8)]
    threads = [_start(settings, i) for i in ids]
    for t in threads:
        t.join(10)
    assert sorted(map(str, runner.finished)) == sorted(map(str, ids))
    assert runner.peak == 1


def test_investigation_jobs_use_their_own_gate(monkeypatch, make_settings):
    started = threading.Event()
    release = threading.Event()
    ran = []

    def fake_investigation(iid, settings):
        ran.append(iid)
        started.set()
        assert release.wait(5)

    monkeypatch.setattr(jobs, "run_investigation", fake_investigation)
    runner = _Runner()
    runner.release.set()
    monkeypatch.setattr(jobs, "run_analysis", runner)
    settings = make_settings(max_concurrent_analyses=1)
    inv = uuid.uuid4()
    t = threading.Thread(target=jobs.start_investigation_job, args=(inv, settings))
    t.start()
    assert started.wait(5)
    jobs.start_analysis_job(uuid.uuid4(), settings)  # an analysis is not blocked by it
    assert len(runner.finished) == 1
    release.set()
    t.join(5)
    assert ran == [inv]
