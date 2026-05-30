"""Refresh worker — mutual exclusion between scheduled + manual runs (E8-S6)."""

import asyncio


async def test_guarded_run_skips_when_locked(monkeypatch):
    """A second _guarded_run while one is in flight must short-circuit."""
    from niouzou.workers import refresh_worker as rw

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_pipeline() -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(rw, "_run_pipeline", _slow_pipeline)

    first = asyncio.create_task(rw._guarded_run())
    await started.wait()
    # Second call should observe `_lock.locked()` and return immediately.
    second = asyncio.create_task(rw._guarded_run())
    await asyncio.wait_for(second, timeout=1.0)

    # The slow first run is still holding the lock.
    assert rw._lock.locked()
    release.set()
    await first


async def test_manual_run_endpoint_reports_already_running(monkeypatch):
    """POST /run mirrors the lock check used by the scheduler."""
    from fastapi.testclient import TestClient

    from niouzou.workers import refresh_worker as rw

    # Don't actually run anything heavy when the lock is acquired.
    async def _noop() -> None:
        return

    monkeypatch.setattr(rw, "_run_pipeline", _noop)

    client = TestClient(rw.app)
    # Acquire the lock manually so /run sees an in-flight run.
    await rw._lock.acquire()
    try:
        resp = client.post("/run")
        assert resp.status_code == 202
        assert resp.json() == {"status": "already_running"}
    finally:
        rw._lock.release()
