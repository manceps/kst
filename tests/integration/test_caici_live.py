"""Live integration test: CAI.CI adapter against the configured endpoint.

Per the no-mocks integration rule, this hits the real CAI.CI endpoint
configured via the ``CAICI_ENDPOINT`` environment variable (and the
optional ``CAICI_API_KEY`` bearer token) and asserts:

- HTTP 200.
- Non-empty response text.
- Telemetry envelope present with at least one canonical signal.

Skipped when ``CAICI_ENDPOINT`` is not set, or when the configured
endpoint is not reachable on the network.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

from kst.adapters import CaiciAdapter
from kst.envelope import AdapterRequest, GreyBoxTelemetry


def _endpoint_from_env() -> str:
    return (
        os.environ.get("CAICI_ENDPOINT", "")
        or os.environ.get("KST_CAICI_ENDPOINT", "")
    )


def _endpoint_reachable(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        sock = socket.create_connection((host, port), timeout=5.0)
        sock.close()
        return True
    except OSError:
        return False


_ENDPOINT = _endpoint_from_env()

pytestmark = pytest.mark.skipif(
    not _ENDPOINT,
    reason=(
        "CAICI_ENDPOINT environment variable is not set; configure it to "
        "the full chat-completions URL (for example "
        "https://chat.cai.ci/v1/chat/completions) to enable the live "
        "integration test."
    ),
)


def test_caici_adapter_live_response_carries_telemetry():
    if not _endpoint_reachable(_ENDPOINT):
        pytest.skip(
            f"CAI.CI endpoint {_ENDPOINT!r} is not reachable from this "
            "environment."
        )
    adapter = CaiciAdapter(max_attempts=2, timeout_s=60.0)
    req = AdapterRequest(
        prompt="Reply with the single word 'ready'.",
        max_tokens=8,
        temperature=0.0,
    )
    resp = adapter.send_adapter(req)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.error}"
    assert resp.text.strip(), "empty response text"
    assert resp.model_id, "empty model_id"
    assert resp.grey_box_telemetry is not None, "no grey_box_telemetry"
    tele = resp.grey_box_telemetry
    assert isinstance(tele, GreyBoxTelemetry)
    # At least one canonical signal should be populated. The CAI.CI
    # inference server emits these on every chat completion.
    populated = [
        tele.epistemic_state,
        tele.confidence,
        tele.competence,
        tele.meta_competence,
    ]
    assert any(v is not None for v in populated), (
        f"telemetry envelope has no canonical signals: {tele!r}"
    )


def test_caici_adapter_live_against_local_inference_server():
    """Local CAI.CI inference server (port 8082) must also work.

    Skipped when port 8082 is not listening.
    """
    try:
        sock = socket.create_connection(("127.0.0.1", 8082), timeout=2.0)
        sock.close()
    except OSError:
        pytest.skip("local inference server on :8082 not listening")
    adapter = CaiciAdapter(
        endpoint="http://localhost:8082/v1/chat/completions",
        max_attempts=2,
        timeout_s=30.0,
    )
    req = AdapterRequest(prompt="ping", max_tokens=8, temperature=0.0)
    resp = adapter.send_adapter(req)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.error}"
    assert resp.text, "empty response text"
    assert resp.grey_box_telemetry is not None, (
        "no grey_box_telemetry from local server"
    )
