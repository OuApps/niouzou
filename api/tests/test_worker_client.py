"""Worker client tests (E19-S4): the API kicks the refresh-worker's pipeline
on source add. The call is best-effort — a worker that's down or busy must
never surface as an error to the caller.

The worker HTTP API is mocked with respx; no real worker is needed.
"""

import httpx
import pytest
import respx

from niouzou.services import worker_client
from niouzou.services.worker_client import WORKER_URL, trigger_pipeline_run


@respx.mock
@pytest.mark.asyncio
async def test_trigger_pipeline_run_started():
    route = respx.post(f"{WORKER_URL}/run").mock(
        return_value=httpx.Response(202, json={"status": "started"})
    )
    assert await trigger_pipeline_run() == "started"
    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_trigger_pipeline_run_already_running():
    respx.post(f"{WORKER_URL}/run").mock(
        return_value=httpx.Response(202, json={"status": "already_running"})
    )
    assert await trigger_pipeline_run() == "already_running"


@respx.mock
@pytest.mark.asyncio
async def test_trigger_pipeline_run_unreachable_never_raises():
    respx.post(f"{WORKER_URL}/run").mock(
        side_effect=httpx.ConnectError("worker down")
    )
    # Best-effort contract: a connection failure resolves to a sentinel, not
    # an exception — the caller's primary action must not break.
    assert await trigger_pipeline_run() == "worker_unavailable"


@respx.mock
@pytest.mark.asyncio
async def test_trigger_pipeline_run_http_error_never_raises():
    respx.post(f"{WORKER_URL}/run").mock(
        return_value=httpx.Response(500, json={"detail": "boom"})
    )
    assert await trigger_pipeline_run() == "worker_unavailable"


def test_worker_url_module_constant_matches():
    # The module exposes the same constant the helper resolves against, so a
    # test can mock the exact URL the call will hit.
    assert worker_client.WORKER_URL == WORKER_URL
