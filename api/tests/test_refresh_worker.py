"""Refresh worker — frugal supervisor: subprocess spawning + mutual exclusion.

E8-S6 gave the worker scheduler/manual mutual exclusion via a shared lock.
E20 moved the heavy pipeline into a one-shot child process; these tests pin the
new contract: the parent spawns ``run_once`` under the lock, never imports
torch, and still debounces concurrent triggers.
"""

import asyncio
import sys


async def test_guarded_run_skips_when_locked(monkeypatch):
    """A second _guarded_run while one is in flight must short-circuit."""
    from niouzou.workers import refresh_worker as rw

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_spawn(*args, **kwargs) -> int:
        started.set()
        await release.wait()
        return 0

    monkeypatch.setattr(rw, "_spawn_run_once", _slow_spawn)

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

    # Don't actually spawn anything when the lock is acquired.
    async def _noop_spawn(*args, **kwargs) -> int:
        return 0

    monkeypatch.setattr(rw, "_spawn_run_once", _noop_spawn)

    client = TestClient(rw.app)
    # Acquire the lock manually so /run sees an in-flight run.
    await rw._lock.acquire()
    try:
        resp = client.post("/run")
        assert resp.status_code == 202
        assert resp.json() == {"status": "already_running"}
    finally:
        rw._lock.release()


async def test_guarded_run_spawns_run_once_subprocess(monkeypatch):
    """The pipeline is executed as ``python -m niouzou.crons.run_once``."""
    from niouzou.workers import refresh_worker as rw

    calls: list[tuple] = []

    class _FakeProc:
        returncode = 0

        async def wait(self) -> int:
            return 0

        def kill(self) -> None:  # pragma: no cover - not hit on a clean run
            pass

    async def _fake_exec(*args, **kwargs):
        calls.append(args)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    await rw._guarded_run()

    assert len(calls) == 1
    # sys.executable -m niouzou.crons.run_once  (no --nightly for the pipeline)
    assert calls[0][0] == sys.executable
    assert calls[0][1:4] == ("-m", "niouzou.crons.run_once")
    assert "--nightly" not in calls[0]


async def test_nightly_job_spawns_run_once_with_nightly_flag(monkeypatch):
    """The nightly refresh runs the same child with ``--nightly``."""
    from niouzou.workers import refresh_worker as rw

    calls: list[tuple] = []

    class _FakeProc:
        returncode = 0

        async def wait(self) -> int:
            return 0

        def kill(self) -> None:  # pragma: no cover
            pass

    async def _fake_exec(*args, **kwargs):
        calls.append(args)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    await rw._nightly_refresh_job()

    assert len(calls) == 1
    assert calls[0][-1] == "--nightly"


async def test_spawn_kills_child_on_timeout(monkeypatch):
    """A child that overruns its timeout is killed and reported as ``-1``."""
    from niouzou.workers import refresh_worker as rw

    killed = asyncio.Event()

    class _WedgedProc:
        returncode = None

        async def wait(self) -> int:
            # Block forever unless killed.
            if killed.is_set():
                return -9
            await asyncio.sleep(3600)
            return 0

        def kill(self) -> None:
            self.returncode = -9
            killed.set()

    async def _fake_exec(*args, **kwargs):
        return _WedgedProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    rc = await rw._spawn_run_once(timeout_s=0.05)
    assert rc == -1
    assert killed.is_set()


def test_worker_module_does_not_import_torch():
    """E20-S2 — the always-on parent must never pull torch transitively.

    The whole point of the frugal worker is that the supervising process keeps
    a floor RSS (~120-150 MB). torch is imported only inside the embedding
    model loader, which lives exclusively in the ``run_once`` child path.
    """
    import niouzou.workers.refresh_worker  # noqa: F401

    assert "torch" not in sys.modules
