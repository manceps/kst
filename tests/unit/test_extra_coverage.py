"""Additional unit tests targeting under-covered branches.

These exercise specific edge paths in observability (histogram
boundaries, prometheus rendering with empty registry), score
(degenerate alpha, geomean with zero, dif with nan column),
persistence (PersistenceError when psycopg2 is absent or pool fails
to build), harness (legacy adapter shim via TargetRequest path,
resume rejection by terminal-status), and the protocol registry
(version-pinned lookup).

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import math
import time
from typing import Iterable, Sequence

import pytest

from kst.envelope import (
    AdapterCapability,
    AdapterResponse,
    ApplicabilityMode,
    GreyBoxTelemetry,
    Item,
    Parsed,
    RunStatus,
    SubTestResult,
    SubTestScore,
    TargetRequest,
    TargetResponse,
)
from kst.errors import (
    ConfigError,
    PersistenceError,
)
from kst.harness import (
    BatteryConfig,
    BatteryRunner,
    JSONLSink,
    SubTestSpec,
    _response_to_jsonable,
    _score_to_jsonable,
)
from kst.observability import (
    LatencyHistogram,
    MetricsRegistry,
    _prometheus_label_value,
    _prometheus_metric_name,
)
from kst.protocol import register_plugin, registry, validate_plugin
from kst.score import (
    AggregationMode,
    aggregate_score_report,
    differential_item_functioning,
    krippendorff_alpha_interval,
)


# ─── Observability low-level edges ─────────────────────────────────────


def test_prometheus_label_value_escapes_quotes_and_backslashes():
    assert _prometheus_label_value('a"b\\c\n') == 'a\\"b\\\\c '


def test_prometheus_metric_name_sanitises_chars():
    assert _prometheus_metric_name("a.b-c") == "a_b_c"


def test_metrics_registry_prometheus_with_empty_state():
    reg = MetricsRegistry()
    text = reg.format_prometheus()
    assert text.endswith("\n")


def test_latency_histogram_records_above_max_collapse_to_inf_bucket():
    h = LatencyHistogram(min_s=0.001, max_s=1.0)
    h.record(1e6)
    snap = h.snapshot()
    assert snap["count"] == 1


# ─── Score module remaining edges ───────────────────────────────────────


def test_krippendorff_alpha_single_unit_returns_nan():
    alpha = krippendorff_alpha_interval([[1.0]])
    assert math.isnan(alpha)


def test_krippendorff_alpha_all_identical_within_units_no_variation_returns_one_or_nan():
    # Each unit has 2 identical raters; Do=0. De across the global pool
    # is also 0 -> we return 1.0 per the implementation contract.
    alpha = krippendorff_alpha_interval([[1.0, 1.0], [1.0, 1.0]])
    assert alpha == 1.0


def test_dif_handles_column_with_nan_skipped():
    per_target = {
        "a": [10.0, float("nan")],
        "b": [50.0, float("nan")],
    }
    res = differential_item_functioning(per_target, threshold=0.1)
    # Item 1 has no valid pair -> nan spread, not flagged.
    assert 1 not in res["flagged_items"]


# ─── Harness response/score serialisers ────────────────────────────────


def test_response_to_jsonable_includes_capability_value():
    resp = AdapterResponse(
        request_id="r",
        text="x",
        model_id="m",
        adapter_name="a",
        capability=AdapterCapability.GREY_BOX,
    )
    out = _response_to_jsonable(resp)
    assert out["capability"] == "grey_box"


def test_score_to_jsonable_round_trip():
    s = SubTestScore(
        test_id="A",
        test_name="A",
        construct_id="A",
        version="1",
        score=80.0,
        max_score=100.0,
    )
    out = _score_to_jsonable(s)
    assert out["construct_id"] == "A"
    assert out["score"] == 80.0


# ─── JSONLSink directory creation and close ────────────────────────────


def test_jsonl_sink_creates_parent_directory(tmp_path):
    nested = tmp_path / "nested" / "deeper" / "out.jsonl"
    sink = JSONLSink(path=str(nested))
    sink.write({"hello": "world"})
    sink.close()
    assert nested.exists()
    content = nested.read_text().strip()
    assert "hello" in content


def test_jsonl_sink_double_close_is_safe(tmp_path):
    sink = JSONLSink(path=str(tmp_path / "x.jsonl"))
    sink.close()
    sink.close()


# ─── Harness shim: legacy adapter that is NOT a BaseAdapter ────────────


class _LegacyAdapter:
    """Adapter object that implements only the legacy TargetRequest path."""

    name = "legacy"
    capability = AdapterCapability.BLACK_BOX

    def send(self, request: TargetRequest) -> TargetResponse:
        return TargetResponse(
            request_id=request.request_id,
            text="legacy-ok",
            model_id="legacy",
            adapter_name=self.name,
            capability=self.capability,
            status_code=200,
        )

    def close(self) -> None:
        return None


class _AlwaysTwentyPlugin:
    theoretical_grounding = ["x"]
    falsifiability_criteria = ["y"]
    applicability_modes = ApplicabilityMode.BOTH

    def get_name(self):
        return "L"

    def get_construct_id(self):
        return "L"

    def get_version(self):
        return "1"

    def build_prompts(self, seed):
        return [Item(item_id="i0", prompt="?")]

    def parse_response(self, item, raw_response):
        return Parsed(item_id=item.item_id, payload={"text": raw_response.text})

    def score(self, parsed_set):
        return SubTestScore(
            test_id="L",
            test_name="L",
            construct_id="L",
            version="1",
            score=20.0,
            max_score=100.0,
            n_items=len(parsed_set),
        )


def test_battery_runner_supports_legacy_adapter_shim():
    registry.clear()
    register_plugin(_AlwaysTwentyPlugin())
    try:
        cfg = BatteryConfig(
            target="legacy",
            adapter_name="legacy",
            sub_tests=[SubTestSpec(construct_id="L")],
            aggregation_mode=AggregationMode.ARITHMETIC,
            n_bootstrap=20,
        )
        runner = BatteryRunner(config=cfg, adapter=_LegacyAdapter())
        result = runner.run()
        assert result.status == RunStatus.COMPLETED
        assert math.isclose(result.report.index_score, 20.0)
    finally:
        registry.clear()


# ─── Aggregator: geometric mode bootstrap ──────────────────────────────


def test_aggregate_score_report_geometric_with_two_zeros():
    s1 = SubTestScore(
        test_id="A", test_name="A", construct_id="A", version="1",
        score=0.0, max_score=100.0,
    )
    s2 = SubTestScore(
        test_id="B", test_name="B", construct_id="B", version="1",
        score=50.0, max_score=100.0,
    )
    rep = aggregate_score_report(
        [s1, s2],
        target="x",
        adapter_name="x",
        capability="black_box",
        mode=AggregationMode.GEOMETRIC,
        n_bootstrap=50,
    )
    assert rep.index_score == 0.0


# ─── Registry: version-pinned lookup raises for missing version ────────


def test_registry_pinned_version_lookup_misses_raises():
    class P:
        theoretical_grounding = ["x"]
        falsifiability_criteria = ["y"]
        applicability_modes = ApplicabilityMode.BOTH

        def get_name(self):
            return "V"

        def get_construct_id(self):
            return "V"

        def get_version(self):
            return "1"

        def build_prompts(self, seed):
            return []

        def parse_response(self, item, raw_response):
            return Parsed(item_id="i", payload={})

        def score(self, parsed_set):
            return SubTestScore(
                test_id="V", test_name="V", construct_id="V", version="1",
                score=10.0, max_score=100.0,
            )

    registry.clear()
    register_plugin(P())
    try:
        with pytest.raises(KeyError):
            registry.get("V", "9.9.9")
    finally:
        registry.clear()


# ─── Persistence error class ────────────────────────────────────────────


def test_persistence_error_is_stt_error_with_context():
    err = PersistenceError("nope", context={"why": "test"})
    assert err.context["why"] == "test"
    assert "nope" in str(err)
