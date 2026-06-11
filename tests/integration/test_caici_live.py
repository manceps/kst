"""Live integration test: CAI.CI adapter against the Cloud Run proxy.

Per the operator's no-mocks integration rule, this hits the real
proxy at chat.cai.ci with a Firebase anonymous token and asserts:

- HTTP 200.
- Non-empty response text.
- Telemetry envelope present with at least the canonical signals.

Skipped only when network egress is unavailable.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import os
import socket

import pytest

from kst.adapters import CaiciAdapter
from kst.envelope import AdapterRequest, GreyBoxTelemetry


def _network_reachable() -> bool:
    try:
        sock = socket.create_connection(
            ("caici-api-proxy-812234591979.us-central1.run.app", 443),
            timeout=5.0,
        )
        sock.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _network_reachable(),
    reason="Cloud Run proxy not reachable in this environment.",
)


def test_caici_adapter_live_response_carries_telemetry():
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
    # At least one canonical signal should be populated. The inference
    # server emits these on every chat completion.
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
        firebase_api_key=None,
        max_attempts=2,
        timeout_s=30.0,
    )
    req = AdapterRequest(prompt="ping", max_tokens=8, temperature=0.0)
    resp = adapter.send_adapter(req)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.error}"
    assert resp.text, "empty response text"
    assert resp.grey_box_telemetry is not None, "no grey_box_telemetry from local server"
