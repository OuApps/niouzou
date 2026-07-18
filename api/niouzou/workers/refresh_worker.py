"""Refresh worker — light always-on supervisor that spawns one-shot children.

Why a separate service? The pipeline is CPU/IO/RAM heavy (newspaper4k parsing,
optional LLM calls per article, the local ~1.2 GB embedding model, batch
INSERTs). Running it inside the main uvicorn process — even as a BackgroundTask
— starves incoming PWA requests on a small Railway instance.

E20 — Frugal worker (the current shape):
    This process is **always-on** but stays **light (~120-150 MB) and never
    imports torch / never loads the embedding model**. The heavy fetch+enrich
    pipeline runs in a short-lived **child process** (``python -m
    niouzou.crons.run_once``) that the worker spawns per run; when the child
    exits the OS reclaims 100 % of its RAM (the only reliable way to give
    torch's resident pages back — an in-process ``unload`` + ``gc`` does not,
    see E17-S4). At rest: no model in memory, RSS at the floor. During a run: a
    brief spike (parent + child) for the few minutes of real work, then back to
    the floor. The nightly refresh runs the same way (``run_once --nightly``).

    The worker keeps its HTTP surface (``/run``, ``/compact/*``, ``/health``)
    and its APScheduler planning; only the *execution* moved to a subprocess.

Scheduling + mutual exclusion (E8-S6, preserved):
    ``_guarded_run`` is shared by the scheduler AND ``POST /run`` — the same
    in-process ``asyncio.Lock`` is held for the **whole lifetime of the child**
    (``await proc.wait()`` under the lock), so a manual trigger during a
    scheduled run (or vice versa) is debounced and only one child ever runs at
    a time. The nightly job and compaction-apply take the same lock, so they
    never overlap the pipeline. A single in-process lock is enough since there
    is exactly one replica; if this ever scales out, swap it for
    ``SELECT pg_try_advisory_lock(...)``.

Telemetry: the child writes ``pipeline_runs`` directly in the DB, so ``/stats``
keeps working unchanged. The child inherits stdout/stderr, so its logs surface
in Railway exactly as before.

Reaper: any article left ``'enriching'`` by a crashed/killed run is reset to
``'pending'`` at the parent's startup (and again at each child's startup) so it
stays visible to the feed and the next run.
"""

import asyncio
import logging
import os
import sys
import sysconfig
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from niouzou.crons.run_once import _reaper_reset_enriching
from niouzou.db import session_scope
from niouzou.models import CompactionRun
from niouzou.models.compaction_run import STATUS_PREVIEW as _COMPACT_PREVIEW
from niouzou.services.compaction_service import CompactionService
from niouzou.services.openrouter_client import OpenRouterClient
from niouzou.services.settings_service import SettingsService

# uvicorn only configures its own loggers; without this our app loggers
# (niouzou.refresh_worker, the child's niouzou.run_once, …) emit nothing at
# INFO level — making the pipeline look stuck.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("niouzou.refresh_worker")

_lock = asyncio.Lock()
# E10-S3 — separate lock for the compaction *preview* phase (LLM call only,
# no DB write). Kept distinct from ``_lock`` so a long LLM grouping call
# doesn't freeze the fetch+enrich pipeline. The ``apply`` phase uses
# ``_lock`` because it rewrites ``article_keywords`` and must not race the
# pipeline's writes.
_compact_lock = asyncio.Lock()
_scheduler: AsyncIOScheduler | None = None

# Hard ceiling on a child's wall-clock runtime. Past this the parent kills the
# child so a wedged run can't hold ``_lock`` (and the feed) forever. The fetch
# +enrich batch is normally a few minutes; the nightly is given more head-room.
_PIPELINE_TIMEOUT_S = 20 * 60
_NIGHTLY_TIMEOUT_S = 60 * 60


# ── page-cache hygiene (E20 follow-up) ──────────────────────────────────────
#
# Killing the run_once child frees its *anonymous* RSS, but every file the
# child mmap'd stays in the container's cgroup **page cache** after it exits —
# and Railway counts page cache in its Memory metric, so idle memory never
# returned to the parent's floor. Two big offenders, measured on the live
# worker: the embedding model (~1.2 GB safetensors) and torch's shared libs
# (libtorch_cpu.so alone is ~440 MB). After each run the parent advises the
# kernel to drop those clean, now-unmapped pages. Verified on Linux: reading a
# file populates page cache, posix_fadvise(DONTNEED) from a fresh fd evicts it
# exactly. The next run re-reads them from local disk (small cold-start,
# already accepted by E20). The parent stays torch-free — it locates torch's
# directory via sysconfig, never importing it. fadvise leaves the parent's own
# still-mapped libs (uvicorn, sqlalchemy…) untouched; only the dead child's
# unmapped pages are reclaimed.


def _hf_cache_dir() -> Path | None:
    """Resolve the HuggingFace cache dir without importing huggingface_hub.

    Mirrors HF's own precedence so the parent stays torch/HF-free. Returns the
    most specific existing dir (the ``hub`` subdir when present), or None.

    Reads ``os.environ`` directly (not via ``config.py``) on purpose: these are
    HuggingFace's *own* env vars, not Niouzou settings — we read them only to
    locate where HF put its cache, the same way ``embedding_service`` reads the
    cgroup/CPU state directly. Adding them to ``Settings`` would misrepresent
    them as Niouzou knobs.
    """
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        value = os.environ.get(var)
        if value and Path(value).exists():
            return Path(value)
    hf_home = os.environ.get("HF_HOME")
    base = Path(hf_home) if hf_home else Path.home() / ".cache" / "huggingface"
    hub = base / "hub"
    if hub.exists():
        return hub
    if base.exists():
        return base
    return None


def _page_cache_dirs() -> list[Path]:
    """Directories whose files the child mmaps and leaves in page cache.

    The HF model cache plus the installed ``torch`` package (its ``lib/*.so``
    are the bulk). torch's path is resolved via sysconfig so the parent never
    imports torch.
    """
    dirs: list[Path] = []
    hf = _hf_cache_dir()
    if hf is not None:
        dirs.append(hf)
    purelib = sysconfig.get_path("purelib")
    if purelib:
        torch_dir = Path(purelib) / "torch"
        if torch_dir.exists():
            dirs.append(torch_dir)
    return dirs


def _drop_run_page_cache() -> None:
    """Evict the model + torch files from the OS page cache (Linux only).

    No-op where ``posix_fadvise`` is absent (macOS/local dev). Best-effort per
    file — a failure on one file must not abort the sweep.
    """
    fadvise = getattr(os, "posix_fadvise", None)
    if fadvise is None:
        return
    dropped = 0
    for cache in _page_cache_dirs():
        for path in cache.rglob("*"):
            try:
                if not path.is_file():
                    continue
                with open(path, "rb") as fh:
                    fadvise(fh.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
                dropped += 1
            except OSError:
                continue
    if dropped:
        logger.info(
            "refresh_worker: evicted %d file(s) from page cache", dropped
        )


# ── subprocess supervision ─────────────────────────────────────────────────


async def _spawn_run_once(*args: str, timeout_s: float) -> int:
    """Spawn the one-shot pipeline child, inherit its stdio, and wait for it.

    Returns the child's exit code (``-1`` if it had to be killed on timeout).
    The child is ``python -m niouzou.crons.run_once`` — it inherits this
    process's environment (DATABASE_URL, OPENROUTER_*, …) and stdout/stderr, so
    no extra wiring is needed and its logs show up in Railway. This is the only
    process in the system that imports torch / loads the embedding model.
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "niouzou.crons.run_once", *args
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.error(
            "refresh_worker: run_once %s exceeded %.0fs — killing",
            args or ("(pipeline)",),
            timeout_s,
        )
        proc.kill()
        await proc.wait()
        return -1
    return proc.returncode if proc.returncode is not None else 0


async def _guarded_run() -> None:
    """Acquire ``_lock`` then spawn the fetch+enrich child; skip if locked.

    The lock is shared with ``POST /run`` so scheduler + manual trigger are
    mutually exclusive. ``_lock.locked()`` is checked before acquiring so we
    never queue a second run behind a slow one — a still-running child means
    this tick is dropped and logged. The lock is held until the child exits.
    """
    if _lock.locked():
        logger.info("refresh_worker: scheduled run skipped — already running")
        return
    async with _lock:
        rc = await _spawn_run_once(timeout_s=_PIPELINE_TIMEOUT_S)
        if rc != 0:
            logger.warning("refresh_worker: pipeline child exited with code %d", rc)
        # Return the model + torch page cache to the OS so idle memory drops
        # back to the parent's floor (off-loop: it walks the cache dirs).
        await asyncio.to_thread(_drop_run_page_cache)


async def _nightly_refresh_job() -> None:
    """Daily weights recompute + dual-score rescore (E16-S9), as a subprocess.

    Takes the same ``_lock`` as the pipeline so the two never overlap (one
    child at a time). The nightly child does NOT load the embedding model.
    """
    async with _lock:
        rc = await _spawn_run_once("--nightly", timeout_s=_NIGHTLY_TIMEOUT_S)
        if rc != 0:
            logger.warning("refresh_worker: nightly child exited with code %d", rc)


def _fetch_trigger(interval_minutes: int) -> CronTrigger:
    """Build a wall-clock-aligned trigger firing every ``interval_minutes``.

    APScheduler's ``minute`` field only accepts a step up to 59, so a naive
    ``CronTrigger(minute="*/{interval}")`` raises ``ValueError`` the moment the
    interval reaches 60 (a perfectly reasonable "hourly" setting) — which
    crashes the worker on startup. Express any interval of a whole hour or more
    on the ``hour`` field instead; sub-hour intervals keep the minute step.
    Non-whole-hour intervals ≥ 60 min round to the nearest hour so the trigger
    stays valid and clock-aligned (an unusual config; the common values are
    15 / 30 / 60).
    """
    interval = max(1, interval_minutes)
    if interval < 60:
        return CronTrigger(minute=f"*/{interval}")
    hours = max(1, round(interval / 60))
    return CronTrigger(hour=f"*/{hours}", minute=0)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire APScheduler with the current cron settings.

    Triggers are CronTrigger (wall-clock aligned) rather than IntervalTrigger
    so the next fire time is predictable — the PWA renders "Next run" against
    the live ``cron_fetch_interval_minutes`` from /stats. The fetch trigger is
    built by ``_fetch_trigger`` so an hourly (≥ 60 min) interval maps onto the
    hour field instead of an invalid ``*/60`` minute step.

    The reaper runs once here, before the scheduler starts, so any article left
    in ``'enriching'`` by a previous crash is rolled back to pending before the
    first scheduled run starts a fresh batch.
    """
    global _scheduler
    reaped = await _reaper_reset_enriching()
    if reaped:
        logger.info(
            "refresh_worker: reaper reset %d enriching → pending on startup",
            reaped,
        )

    async with session_scope() as session:
        cfg = await SettingsService(session).get_effective()

    interval = max(1, cfg.cron_fetch_interval)
    nightly_hour = cfg.cron_nightly_refresh_hour

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _guarded_run,
        _fetch_trigger(interval),
        id="fetch_enrich",
        # A worker restart close to the next slot must not skip it.
        misfire_grace_time=300,
        coalesce=True,
    )
    _scheduler.add_job(
        _nightly_refresh_job,
        CronTrigger(hour=nightly_hour, minute=0),
        id="nightly_refresh",
        # The daily job can tolerate a generous grace window — a one-hour
        # restart shouldn't make us lose a run.
        misfire_grace_time=3600,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "refresh_worker: scheduler started (fetch_enrich=*/%d min, nightly_refresh=%02d:00 UTC)",
        interval,
        nightly_hour,
    )
    try:
        yield
    finally:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None


app = FastAPI(title="Niouzou Refresh Worker", version="0.1.0", lifespan=_lifespan)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Compaction endpoints (E10-S3) ────────────────────────────────────────


class _CompactApplyBody(BaseModel):
    id: uuid.UUID


@app.post("/compact/preview", status_code=status.HTTP_202_ACCEPTED)
async def compact_preview() -> JSONResponse:
    """Generate a keyword-merge preview (LLM only — no DB write yet).

    ``_compact_lock`` is held for the duration of the LLM call so a second
    preview can't race the first; the pipeline ``_lock`` is left free so
    fetch+enrich keeps running while the LLM is thinking.
    """
    if _compact_lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )
    async with _compact_lock:
        async with session_scope() as session:
            cfg = await SettingsService(session).get_effective()
        client = OpenRouterClient.from_overrides(
            cfg.openrouter_api_key, cfg.openrouter_model
        )
        if client is None:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "ai_disabled",
                    "message": "Compaction requires an OpenRouter API key.",
                },
            )
        try:
            async with session_scope() as session:
                run = await CompactionService(session, client).preview()
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "id": str(run.id),
                        "groups": run.groups_json,
                    },
                )
        finally:
            client.close()


@app.post("/compact/apply", status_code=status.HTTP_202_ACCEPTED)
async def compact_apply(body: _CompactApplyBody) -> JSONResponse:
    """Apply a previously-generated preview.

    Uses the *pipeline* ``_lock`` (not ``_compact_lock``): the apply rewrites
    ``article_keywords`` and reruns the weight recompute. Doing that while a
    fetch+enrich pipeline is also writing rows would corrupt both.

    The run id is validated *before* the 202 is returned so a stale id from
    the admin UI (already applied / rejected / unknown) surfaces as a 404
    instead of silently logging a background failure ten seconds later.
    """
    async with session_scope() as session:
        run = await session.get(CompactionRun, body.id)
        if run is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "not_found", "message": "Compaction run not found"},
            )
        if run.status != _COMPACT_PREVIEW:
            # 409 because the resource exists but is in a terminal state — the
            # caller's request is well-formed but no longer applicable.
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error": "invalid_state",
                    "message": f"Compaction run is not a preview (status={run.status!r})",
                },
            )

    if _lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )
    asyncio.create_task(_apply_in_background(body.id))
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content={"status": "started"}
    )


async def _apply_in_background(run_id: uuid.UUID) -> None:
    """Acquire the pipeline lock and run ``CompactionService.apply``.

    LLM + DB only (no torch), so this stays in the parent rather than going
    through ``run_once``; the pipeline ``_lock`` keeps it exclusive with runs.
    """
    async with _lock:
        try:
            async with session_scope() as session:
                await CompactionService(session).apply(run_id)
                logger.info("refresh_worker: compaction %s applied", run_id)
        except Exception:
            logger.exception(
                "refresh_worker: compaction apply failed for %s", run_id
            )


@app.delete(
    "/compact/{run_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def compact_reject(run_id: uuid.UUID) -> JSONResponse:
    """Mark a preview as rejected (no DB rewrites)."""
    try:
        async with session_scope() as session:
            await CompactionService(session).reject(run_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "not_found", "message": str(exc)},
        )
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


@app.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run() -> JSONResponse:
    """Trigger the fetch+enrich pipeline.

    Returns immediately with ``{"status": "already_running"}`` if a previous
    run is still in flight; otherwise spawns ``_guarded_run`` as a task and
    returns ``{"status": "started"}``. The exact same ``_lock`` guards the
    scheduled path, so the two entry points never race.
    """
    if _lock.locked():
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "already_running"},
        )
    asyncio.create_task(_guarded_run())
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content={"status": "started"}
    )
