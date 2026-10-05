"""Unit tests for kst.adapters.

Covers retry / rate-limit / timeout behavior in BaseAdapter via a
locally-constructed test adapter (NOT a vendor SDK mock; we
deterministically inject failures into the subclass's ``_send_once``).
Covers the CAI.CI envelope mapping function in isolation.

The OpenAI / Anthropic / Google / HF adapters all share BaseAdapter,
so coverage of the BaseAdapter retry / backoff path covers them too.
Vendor-specific HTTP shape is exercised in the live integration tests.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import random
import time

import pytest

from kst.adapters.base import BaseAdapter, _RateLimiter
from kst.adapters.caici_adapter import (
    _FirebaseTokenManager,
    map_cognitive_telemetry,
)
from kst.adapters.openai_adapter import OpenAIAdapter
from kst.adapters.anthropic_adapter import AnthropicAdapter
from kst.adapters.google_adapter import GoogleAdapter
from kst.adapters.caici_adapter import CaiciAdapter
from kst.envelope import (
    AdapterCapabilities,
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    GreyBoxTelemetry,
)
from kst.errors import (
    AdapterError,
    RateLimitError,
    TimeoutError as KSTTimeoutError,
)


# ─── _RateLimiter ───────────────────────────────────────────────────────


def test_rate_limiter_noop_when_rpm_none():
    rl = _RateLimiter(None)
    start = time.monotonic()
    rl.acquire()
    rl.acquire()
    assert time.monotonic() - start < 0.05


def test_rate_limiter_spaces_calls():
    rl = _RateLimiter(rpm=600)  # 1 call per 100 ms.
    rl.acquire()
    start = time.monotonic()
    rl.acquire()
    gap = time.monotonic() - start
    assert gap >= 0.08  # tolerate a little jitter


# ─── BaseAdapter behaviour: retry, backoff, eventual failure ────────────


class _DummyAdapter(BaseAdapter):
    """Adapter that mutates its behavior across calls for testing."""

    name = "dummy"
    capability = AdapterCapability.BLACK_BOX
    DEFAULT_MAX_ATTEMPTS = 3
    DEFAULT_BACKOFF_BASE_S = 0.01
    DEFAULT_BACKOFF_MAX_S = 0.05

    def __init__(self, behaviors):
        super().__init__(
            timeout_s=1.0,
            max_attempts=3,
            backoff_base_s=0.01,
            backoff_max_s=0.05,
            rng=random.Random(42),
        )
        self.behaviors = list(behaviors)
        self.calls = 0

    def _send_once(self, request):
        self.calls += 1
        action = self.behaviors.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


def _ok_response(req: AdapterRequest, text: str = "ok") -> AdapterResponse:
    return AdapterResponse(
        request_id=req.request_id,
        text=text,
        model_id="m",
        adapter_name="dummy",
        capability=AdapterCapability.BLACK_BOX,
        status_code=200,
    )


def test_base_adapter_succeeds_first_try():
    req = AdapterRequest(prompt="x")
    ok = _ok_response(req)
    adapter = _DummyAdapter([ok])
    resp = adapter.send_adapter(req)
    assert resp.text == "ok"
    assert resp.attempts == 1
    assert adapter.calls == 1


def test_base_adapter_retries_rate_limit_then_succeeds():
    req = AdapterRequest(prompt="x")
    ok = _ok_response(req)
    adapter = _DummyAdapter(
        [
            RateLimitError("slow", adapter="dummy", retry_after_s=0.01),
            ok,
        ]
    )
    resp = adapter.send_adapter(req)
    assert resp.text == "ok"
    assert resp.attempts == 2
    assert adapter.calls == 2


def test_base_adapter_retries_5xx_then_succeeds():
    req = AdapterRequest(prompt="x")
    ok = _ok_response(req)
    adapter = _DummyAdapter(
        [
            AdapterError("transient", adapter="dummy", status_code=502),
            ok,
        ]
    )
    resp = adapter.send_adapter(req)
    assert resp.text == "ok"
    assert resp.attempts == 2


def test_base_adapter_does_not_retry_4xx():
    req = AdapterRequest(prompt="x")
    adapter = _DummyAdapter(
        [
            AdapterError("bad request", adapter="dummy", status_code=400),
        ]
    )
    resp = adapter.send_adapter(req)
    # 4xx (non-429) is non-retryable -> single attempt then error response.
    assert adapter.calls == 1
    assert resp.status_code == 400
    assert "AdapterError" in (resp.error or "")


def test_base_adapter_exhausts_retries_and_returns_error_response():
    req = AdapterRequest(prompt="x")
    adapter = _DummyAdapter(
        [
            KSTTimeoutError("t1", adapter="dummy"),
            KSTTimeoutError("t2", adapter="dummy"),
            KSTTimeoutError("t3", adapter="dummy"),
        ]
    )
    resp = adapter.send_adapter(req)
    assert resp.text == ""
    assert resp.attempts == 3
    assert resp.status_code == 599 or resp.status_code == 0 or resp.status_code is None
    assert "TimeoutError" in (resp.error or "")


def test_base_adapter_catches_unhandled_exception():
    req = AdapterRequest(prompt="x")
    adapter = _DummyAdapter(
        [
            RuntimeError("totally unexpected"),
            RuntimeError("again"),
            RuntimeError("and again"),
        ]
    )
    resp = adapter.send_adapter(req)
    assert "RuntimeError" in (resp.error or "")
    assert resp.attempts == 3


def test_base_adapter_send_back_compat_translates_to_target_response():
    req = AdapterRequest(prompt="x")
    ok = _ok_response(req)
    adapter = _DummyAdapter([ok])
    # Legacy TargetRequest path.
    from kst.envelope import TargetRequest
    legacy_req = TargetRequest(prompt="x", request_id=req.request_id)
    legacy_resp = adapter.send(legacy_req)
    assert legacy_resp.text == "ok"
    assert legacy_resp.status_code == 200


# ─── Backoff math ───────────────────────────────────────────────────────


def test_base_adapter_compute_backoff_caps_at_max():
    adapter = _DummyAdapter([_ok_response(AdapterRequest(prompt="x"))])
    # With base 0.01, attempt 100 should still be capped at 0.05.
    backoff = adapter._compute_backoff(100)
    assert 0.0 <= backoff <= 0.05


def test_base_adapter_compute_rate_limit_backoff_honours_retry_after():
    adapter = _DummyAdapter([_ok_response(AdapterRequest(prompt="x"))])
    exc = RateLimitError("slow", retry_after_s=0.02)
    wait = adapter._compute_rate_limit_backoff(exc, 1)
    assert wait == 0.02


def test_base_adapter_compute_rate_limit_backoff_falls_back_when_absent():
    adapter = _DummyAdapter([_ok_response(AdapterRequest(prompt="x"))])
    exc = RateLimitError("slow", retry_after_s=None)
    wait = adapter._compute_rate_limit_backoff(exc, 1)
    # _DummyAdapter does not declare an rpm, so the rate-window floor
    # is disabled and the wait is bounded by ``backoff_max_s``.
    assert 0.0 <= wait <= 0.05


class _RpmDummyAdapter(BaseAdapter):
    """A dummy adapter that declares a real rpm so the rate-window
    floor in :meth:`BaseAdapter._compute_rate_limit_backoff` is active.
    """

    name = "dummy_rpm"
    capability = AdapterCapability.BLACK_BOX

    def __init__(self, rpm: int, backoff_max_s: float = 1000.0) -> None:
        super().__init__(
            timeout_s=1.0,
            max_attempts=3,
            backoff_base_s=0.01,
            backoff_max_s=backoff_max_s,
            rpm=rpm,
            rng=random.Random(42),
        )

    def _send_once(self, request):  # pragma: no cover - never invoked
        raise NotImplementedError


def test_compute_rate_limit_backoff_floors_at_one_full_rpm_window():
    """When no Retry-After is supplied, the wait must be at least one
    full rate-window per retry attempt so retry-N lands in retry-N's
    own fresh budget bucket. With rpm=60 the window is 1.0s, so
    attempt=1 floors at 1.0s, attempt=2 at 2.0s, attempt=3 at 3.0s.
    """
    adapter = _RpmDummyAdapter(rpm=60, backoff_max_s=1000.0)
    exc = RateLimitError("rl", retry_after_s=None)

    wait1 = adapter._compute_rate_limit_backoff(exc, 1)
    wait2 = adapter._compute_rate_limit_backoff(exc, 2)
    wait3 = adapter._compute_rate_limit_backoff(exc, 3)

    assert wait1 >= 1.0
    assert wait2 >= 2.0
    assert wait3 >= 3.0


def test_compute_rate_limit_backoff_window_floor_disabled_when_rpm_unset():
    """When rpm is None / 0 the window floor is disabled; the existing
    jittered exponential backoff path is preserved unchanged.
    """
    adapter = _DummyAdapter([_ok_response(AdapterRequest(prompt="x"))])
    # _DummyAdapter sets rpm=None so the floor branch must not engage.
    assert adapter._rate_limiter._rpm is None
    exc = RateLimitError("rl", retry_after_s=None)
    wait = adapter._compute_rate_limit_backoff(exc, 3)
    # Bounded by backoff_max_s; rpm floor would have forced wait >= 3.0.
    assert wait <= 0.05


def test_compute_rate_limit_backoff_honours_retry_after_over_floor():
    """An explicit Retry-After short-circuits the rate-window floor:
    when the vendor tells us exactly how long to wait, that wins.
    """
    adapter = _RpmDummyAdapter(rpm=60, backoff_max_s=1000.0)
    exc = RateLimitError("rl", retry_after_s=0.1)
    wait = adapter._compute_rate_limit_backoff(exc, 5)
    assert wait == pytest.approx(0.1)


# ─── Capabilities declarations ──────────────────────────────────────────


def test_openai_adapter_capabilities():
    a = OpenAIAdapter(api_key="x")
    caps = a.get_capabilities()
    assert caps.supports_seed is True
    assert caps.supports_logprobs is True
    assert caps.default_model_id


def test_anthropic_adapter_capabilities():
    a = AnthropicAdapter(api_key="x")
    caps = a.get_capabilities()
    assert caps.supports_seed is False
    assert caps.default_model_id


def test_google_adapter_capabilities():
    a = GoogleAdapter(api_key="x")
    caps = a.get_capabilities()
    assert caps.default_model_id


def test_caici_adapter_capabilities_declares_grey_box():
    a = CaiciAdapter(firebase_api_key=None, endpoint="http://localhost:8082")
    caps = a.get_capabilities()
    assert caps.capability == AdapterCapability.GREY_BOX
    assert caps.supports_grey_box_telemetry is True


# ─── CAI.CI envelope mapping ────────────────────────────────────────────


def test_map_cognitive_telemetry_full_envelope():
    payload = {
        "epistemic_state": "uncertain",
        "confidence": 0.5,
        "verified_confidence": 0.55,
        "valence": -0.1,
        "arousal": 0.7,
        "seeking_drive": 0.3,
        "competence": 0.9,
        "meta_competence": 0.6,
        "workspace_selectivity": 0.4,
        "adaptive_temperature": {"tier": "client_override"},
        "grounding_drift_block": {"action": "pass"},
        "factual_claim_audit": {"gate_decision": "ALLOW"},
        "tool_routing": {"strategy": "direct_generate"},
        "voice": {"intensity": 0.2},
    }
    t = map_cognitive_telemetry(payload)
    assert isinstance(t, GreyBoxTelemetry)
    assert t.epistemic_state == "uncertain"
    assert t.confidence == 0.5
    assert t.calibration_score == 0.55
    assert t.ags_state == "client_override"
    assert t.ags_drift_flag is False
    assert t.factual_claim_audit == {"gate_decision": "ALLOW"}
    assert t.tool_routing["strategy"] == "direct_generate"


def test_map_cognitive_telemetry_handles_missing_fields():
    t = map_cognitive_telemetry({})
    assert t.epistemic_state is None
    assert t.confidence is None
    assert t.raw == {}


# ─── Firebase token manager unit (no network) ───────────────────────────


def test_firebase_token_manager_constructor_records_api_key():
    mgr = _FirebaseTokenManager(api_key="X")
    assert mgr.uid is None
    assert mgr._api_key == "X"


# ─── OpenAI / Anthropic / Google: missing API key ──────────────────────


def test_openai_send_once_without_key_raises_adapter_error():
    a = OpenAIAdapter(api_key="")
    req = AdapterRequest(prompt="x")
    with pytest.raises(AdapterError):
        a._send_once(req)


def test_anthropic_send_once_without_key_raises_adapter_error():
    a = AnthropicAdapter(api_key="")
    req = AdapterRequest(prompt="x")
    with pytest.raises(AdapterError):
        a._send_once(req)


def test_google_send_once_without_key_raises_adapter_error():
    a = GoogleAdapter(api_key="")
    req = AdapterRequest(prompt="x")
    with pytest.raises(AdapterError):
        a._send_once(req)
