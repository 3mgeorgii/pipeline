"""End-to-end tests for the worker base class and stub pipeline."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import pytest

from bot.jobs import Job, JobQueue
from bot.workers.analyzer import AnalyzerWorker
from bot.workers.base import Worker
from bot.workers.editor import EditorWorker
from bot.workers.seo import SeoWorker


@pytest.fixture
async def queue(tmp_path: Path) -> JobQueue:
    q = JobQueue(tmp_path / "jobs.db")
    await q.init()
    return q


class _RecordingWorker(Worker):
    """Test worker that records every job it processed and lets us assert order."""

    kind = "test_kind"
    next_kind = None

    def __init__(self, queue: JobQueue, **kw: Any) -> None:
        super().__init__(queue, **kw)
        self.processed: list[int] = []

    async def process(self, job: Job) -> dict[str, Any]:
        self.processed.append(job.id)
        return {"ok": True, "id": job.id}


async def _drain(worker: Worker, *, timeout: float = 2.0) -> None:
    """Run ``worker`` until the queue has no jobs of its kind, then stop."""

    async def _runner() -> None:
        await worker.run()

    task = asyncio.create_task(_runner())
    deadline = asyncio.get_event_loop().time() + timeout
    try:
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.05)
            remaining = await worker.queue.list_active()
            if not any(j.kind == worker.kind for j in remaining):
                break
    finally:
        worker.stop()
        await task


async def test_worker_processes_queued_job(queue: JobQueue) -> None:
    worker = _RecordingWorker(queue, poll_interval_s=0.05)
    job_id = await queue.enqueue("test_kind", {"v": 1}, chat_id=1)
    await _drain(worker)

    assert worker.processed == [job_id]
    job = await queue.get(job_id)
    assert job is not None
    assert job.status == "done"
    assert job.result == {"ok": True, "id": job_id}


async def test_worker_marks_failed_on_exception(queue: JobQueue) -> None:
    class _Boom(Worker):
        kind = "test_kind"

        async def process(self, job: Job) -> dict[str, Any]:
            raise RuntimeError("kaboom")

    worker = _Boom(queue, poll_interval_s=0.05)
    job_id = await queue.enqueue("test_kind", {}, chat_id=1)
    await _drain(worker)

    job = await queue.get(job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error is not None
    assert "kaboom" in job.error
    assert job.retries == 1


async def test_worker_survives_db_error_in_handle(queue: JobQueue) -> None:
    """The polling loop must not die when ``mark_done`` raises (e.g. SQLite BUSY)."""

    original_mark_done = queue.mark_done
    failures = {"left": 1}

    async def flaky_mark_done(job_id: int, result: dict[str, Any]) -> None:
        if failures["left"] > 0:
            failures["left"] -= 1
            raise RuntimeError("simulated SQLite BUSY")
        await original_mark_done(job_id, result)

    queue.mark_done = flaky_mark_done  # type: ignore[method-assign]

    worker = _RecordingWorker(queue, poll_interval_s=0.05)
    first = await queue.enqueue("test_kind", {"v": 1}, chat_id=1)
    second = await queue.enqueue("test_kind", {"v": 2}, chat_id=1)
    await _drain(worker, timeout=3.0)

    # The first job's mark_done blew up; the worker must not have crashed,
    # so the second job still got processed.
    assert second in worker.processed
    job2 = await queue.get(second)
    assert job2 is not None
    assert job2.status == "done"
    # First job's status row stays at ``running`` because mark_done failed.
    job1 = await queue.get(first)
    assert job1 is not None
    assert job1.status == "running"


async def test_worker_chains_to_next_kind(queue: JobQueue) -> None:
    class _Producer(Worker):
        kind = "test_kind"
        next_kind = "next_kind"

        async def process(self, job: Job) -> dict[str, Any]:
            return {"echoed": job.payload}

    producer = _Producer(queue, poll_interval_s=0.05)
    job_id = await queue.enqueue("test_kind", {"x": 1}, chat_id=42)
    await _drain(producer)

    parent = await queue.get(job_id)
    assert parent is not None
    assert parent.status == "done"

    children = await queue.list_active(chat_id=42)
    assert len(children) == 1
    child = children[0]
    assert child.kind == "next_kind"
    assert child.parent_id == job_id
    assert child.payload == {"echoed": {"x": 1}}


async def test_full_pipeline_runs_through_stages(queue: JobQueue) -> None:
    """Smoke test: starting at ``analyze`` we end with 3 publish jobs queued.

    We skip the ``download`` stage here because :class:`DownloaderWorker` now
    really shells out to yt-dlp; coverage for it lives in
    ``tests/test_downloader.py``. This test still covers the orchestration
    contract: 1 analyze → 3 edit → 3 seo → 3 publish via parent_id chains.
    """
    workers = [
        AnalyzerWorker(queue, poll_interval_s=0.05),
        EditorWorker(queue, poll_interval_s=0.05),
        SeoWorker(queue, poll_interval_s=0.05),
    ]
    tasks = [asyncio.create_task(w.run()) for w in workers]

    job_id = await queue.enqueue(
        "analyze",
        {"source_path": "/tmp/lilush/sources/fake.mp4", "duration_s": 5400},
        chat_id=999,
    )

    # Wait for the chain: analyze → 3 edit → 3 seo → 3 publish (queued).
    deadline = asyncio.get_event_loop().time() + 30.0
    try:
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)
            jobs = await queue.list_by_chat(999, limit=50)
            publishers = [j for j in jobs if j.kind == "publish"]
            seos_done = [j for j in jobs if j.kind == "seo" and j.status == "done"]
            if len(publishers) == 3 and len(seos_done) == 3:
                break
    finally:
        for w in workers:
            w.stop()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

    jobs = await queue.list_by_chat(999, limit=50)
    by_kind = {
        k: [j for j in jobs if j.kind == k]
        for k in ("analyze", "edit", "seo", "publish")
    }

    assert len(by_kind["analyze"]) == 1
    assert by_kind["analyze"][0].status == "done"
    assert len(by_kind["edit"]) == 3
    assert all(j.status == "done" for j in by_kind["edit"])
    assert len(by_kind["seo"]) == 3
    assert all(j.status == "done" for j in by_kind["seo"])
    assert len(by_kind["publish"]) == 3
    # Publishers are queued or done — they need a Bot to send messages, so
    # they may sit at "queued" state when no PublisherWorker runs.
    assert all(j.status in {"queued", "running"} for j in by_kind["publish"])

    parent = await queue.get(job_id)
    assert parent is not None
    assert parent.status == "done"
