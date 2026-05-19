"""Unit tests for kst.envelope and kst.errors.

These cover dataclass invariants, JSON round-tripping, the production
error taxonomy carrying structured context, and the legacy <-> new
type bridges.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import json

import pytest

from kst.envelope import (
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    GreyBoxTelemetry,
    HarnessReport,
    Item,
    Parsed,
    RunStatus,
    ScoreInterval,
    SubTestResult,
    SubTestScore,
    TargetRequest,
    TargetResponse,
    capture_traceback,
    from_dict_report,
)
from kst.errors import (
    AdapterError,
    ConfigError,
    IncompleteBatteryError,
    PersistenceError,
    PluginContractError,
    RateLimitError,
    ResumeError,
    KSTError,
    ScoreValidationError,
    TimeoutError as KSTTimeoutError,
)


# ─── Envelope round-trips ───────────────────────────────────────────────


def test_adapter_request_to_target_request_round_trip():
    req = AdapterRequest(
        prompt="hello",
        system="be terse",
        construct_id="KMR_ADV",
        item_id="i_001",
        sub_test_version="1.0.0",
        temperature=0.0,
        max_tokens=128,
        seed=42,
        request_logprobs=True,
        stop_sequences=["</s>"],
        metadata={"stratum": 2},
    )
    legacy = req.to_target_request()
    assert legacy.prompt == "hello"
    assert legacy.system == "be terse"
    assert legacy.metadata["construct_id"] == "KMR_ADV"
    assert legacy.metadata["seed"] == 42
    assert legacy.metadata["request_logprobs"] is True
    assert legacy.metadata["stop_sequences"] == ["</s>"]

    re_req = AdapterRequest.from_target_request(legacy)
    assert re_req.construct_id == "KMR_ADV"
    assert re_req.item_id == "i_001"
    assert re_req.seed == 42
    assert re_req.request_logprobs is True
    assert re_req.stop_sequences == ["</s>"]
    assert re_req.metadata.get("stratum") == 2


def test_adapter_response_from_target_response_preserves_telemetry():
    tele = GreyBoxTelemetry(epistemic_state="know", confidence=0.92)
    legacy = TargetResponse(
        request_id="rid_1",
        text="hi",
        model_id="m",
        adapter_name="a",
        capability=AdapterCapability.GREY_BOX,
        status_code=200,
        telemetry=tele,
        raw={"ok": True},
    )
    resp = AdapterResponse.from_target_response(legacy)
    assert resp.text == "hi"
    assert resp.grey_box_telemetry is tele
    assert resp.telemetry is tele  # the property alias


def test_sub_test_score_normalized_clamps_and_handles_zero_max():
    s = SubTestScore(
        test_id="t",
        test_name="t",
        construct_id="C",
        version="1",
        score=120.0,
        max_score=100.0,
    )
    assert s.normalized == 100.0
    s.score = -5.0
    assert s.normalized == 0.0
    s.max_score = 0.0
    assert s.normalized == 0.0


def test_sub_test_score_to_sub_test_result_back_compat():
    s = SubTestScore(
        test_id="t",
        test_name="T",
        construct_id="C",
        version="1.0",
        score=80.0,
        max_score=100.0,
        sub_scores={"sub1": 0.5},
        notes="note",
        duration_s=1.23,
    )
    legacy = s.to_sub_test_result()
    assert isinstance(legacy, SubTestResult)
    assert legacy.test_name == "T"
    assert legacy.score == 80.0
    assert legacy.sub_scores == {"sub1": 0.5}
    assert legacy.duration_s == 1.23


def test_score_interval_width():
    ci = ScoreInterval(lower=10.0, upper=20.0, confidence=0.95, n_bootstrap=1000)
    assert ci.width() == 10.0


def test_harness_report_to_markdown_and_json_round_trip():
    rep = HarnessReport(
        target="caici",
        adapter_name="caici",
        capability=AdapterCapability.GREY_BOX,
    )
    rep.sub_tests.append(
        SubTestResult(
            test_id="t1",
            test_name="Test 1",
            score=50.0,
            max_score=100.0,
            notes="ok",
        )
    )
    rep.index_score = 50.0
    md = rep.to_markdown()
    assert "KST Index report: caici" in md
    js = rep.to_json()
    data = json.loads(js)
    assert data["target"] == "caici"
    rep2 = from_dict_report(data)
    assert rep2.target == "caici"
    assert rep2.capability == AdapterCapability.GREY_BOX
    assert rep2.sub_tests[0].test_id == "t1"


def test_from_dict_report_drops_unknown_keys_and_handles_nested_telemetry():
    payload = {
        "target": "x",
        "adapter_name": "a",
        "capability": "grey_box",
        "sub_tests": [
            {
                "test_id": "t",
                "test_name": "T",
                "score": 70.0,
                "max_score": 100.0,
                "requests": [
                    {
                        "prompt": "p",
                        "request_id": "r1",
                        "temperature": 0.1,
                        "max_tokens": 16,
                        "test_id": "t",
                        "metadata": {},
                        "unknown_field": "ignored",
                    }
                ],
                "responses": [
                    {
                        "request_id": "r1",
                        "text": "ok",
                        "model_id": "m",
                        "adapter_name": "a",
                        "capability": "grey_box",
                        "status_code": 200,
                        "telemetry": {
                            "epistemic_state": "know",
                            "confidence": 0.9,
                            "future_field": "ignored",
                        },
                        "extra_unknown": "dropped",
                    }
                ],
            }
        ],
    }
    rep = from_dict_report(payload)
    assert rep.target == "x"
    assert rep.sub_tests[0].responses[0].telemetry.confidence == 0.9


def test_run_status_round_trips_through_value():
    assert RunStatus("running") is RunStatus.RUNNING
    assert RunStatus.COMPLETED.value == "completed"


def test_capture_traceback_returns_non_empty_string():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        tb = capture_traceback(exc)
    assert "ValueError" in tb
    assert "boom" in tb


# ─── Errors ────────────────────────────────────────────────────────────


def test_stt_error_to_dict_keeps_context():
    err = KSTError("nope", context={"reason": "x"})
    payload = err.to_dict()
    assert payload["class"] == "KSTError"
    assert payload["context"]["reason"] == "x"


def test_adapter_error_context_records_adapter_and_status():
    err = AdapterError("boom", adapter="caici", status_code=500)
    assert err.adapter == "caici"
    assert err.status_code == 500
    assert err.context["adapter"] == "caici"
    assert err.context["status_code"] == 500


def test_rate_limit_error_carries_retry_after():
    err = RateLimitError("slow", adapter="openai", retry_after_s=2.5)
    assert err.retry_after_s == 2.5
    assert err.context["retry_after_s"] == 2.5
    assert err.status_code == 429


def test_incomplete_battery_error_records_missing_constructs():
    err = IncompleteBatteryError(
        "missing", expected=5, actual=3, missing=["a", "b"]
    )
    assert err.expected == 5
    assert err.actual == 3
    assert err.missing == ["a", "b"]
    assert err.context["missing"] == ["a", "b"]


def test_score_validation_error_is_an_stt_error():
    assert issubclass(ScoreValidationError, KSTError)
    assert issubclass(ConfigError, KSTError)
    assert issubclass(PluginContractError, KSTError)
    assert issubclass(PersistenceError, KSTError)
    assert issubclass(ResumeError, KSTError)
    assert issubclass(KSTTimeoutError, AdapterError)
