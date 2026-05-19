"""Unit tests for kst.harness.

Covers BatteryRunner config validation, plugin resolution against
the registry, isolation (one bad sub-test does not corrupt others),
timeout enforcement, JSONL sink writes, and the report's index_score
math end-to-end against a deterministic in-process adapter.

The persistence layer is not exercised here (live PostgreSQL is in
the integration suite); the runner accepts ``persistence=None`` and
the JSONL sink alone is sufficient to certify the orchestration path.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from typing import Iterable, List, Sequence

import pytest

from kst.adapters.base import BaseAdapter
from kst.envelope import (
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    RunStatus,
    SubTestScore,
)
from kst.errors import ConfigError
from kst.harness import (
    BatteryConfig,
    BatteryRunner,
    JSONLSink,
    SubTestSpec,
    _environment_metadata,
)
from kst.protocol import register_plugin, registry
from kst.score import AggregationMode


class EchoAdapter(BaseAdapter):
    """Deterministic in-process adapter for unit tests."""

    name = "echo"
    capability = AdapterCapability.BLACK_BOX

    def __init__(self):
        super().__init__(timeout_s=2.0, max_attempts=1)

    def _send_once(self, request: AdapterRequest) -> AdapterResponse:
        return AdapterResponse(
            request_id=request.request_id,
            text=f"echo:{request.prompt}",
            model_id="echo-1",
            adapter_name=self.name,
            capability=self.capability,
            status_code=200,
        )


class FixedScorePlugin:
    """Sub-test plugin that always reports a fixed normalized score."""

    theoretical_grounding = ["Cite 2024"]
    falsifiability_criteria = ["score outside [0,100]"]
    applicability_modes = ApplicabilityMode.BOTH

    def __init__(
        self,
        construct_id: str = "FIX",
        version: str = "1",
        score: float = 60.0,
        n_items: int = 3,
    ) -> None:
        self._construct_id = construct_id
        self._version = version
        self._score = score
        self._n_items = n_items

    def get_name(self) -> str:
        return self._construct_id

    def get_construct_id(self) -> str:
        return self._construct_id

    def get_version(self) -> str:
        return self._version

    def build_prompts(self, seed: int) -> Iterable[Item]:
        return [
            Item(item_id=f"i_{i}", prompt=f"prompt_{i}", seed=seed)
            for i in range(self._n_items)
        ]

    def parse_response(self, item: Item, raw_response: AdapterResponse) -> Parsed:
        return Parsed(item_id=item.item_id, payload={"text": raw_response.text})

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore:
        return SubTestScore(
            test_id=self._construct_id,
            test_name=self._construct_id,
            construct_id=self._construct_id,
            version=self._version,
            score=self._score,
            max_score=100.0,
            n_items=len(parsed_set),
        )


class BoomPlugin(FixedScorePlugin):
    """Sub-test plugin whose ``score()`` raises mid-battery."""

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore:
        raise RuntimeError("intentional failure")


class SlowPlugin(FixedScorePlugin):
    """Sub-test plugin that sleeps long enough to trip the timeout."""

    def build_prompts(self, seed):
        time.sleep(5.0)
        return []


class GreyOnlyPlugin(FixedScorePlugin):
    applicability_modes = ApplicabilityMode.GREY_BOX


@pytest.fixture(autouse=True)
def _clear_registry():
    registry.clear()
    yield
    registry.clear()


# ─── Config validation ─────────────────────────────────────────────────


def test_battery_runner_rejects_empty_sub_tests():
    cfg = BatteryConfig(target="t", adapter_name="echo", sub_tests=[])
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.FAILED
    assert "ConfigError" in (result.error or "")
    assert result.report is None


def test_battery_runner_rejects_zero_parallelism():
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[SubTestSpec(construct_id="X")],
        parallelism=0,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.FAILED
    assert "ConfigError" in (result.error or "")


def test_battery_runner_rejects_missing_plugin():
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[SubTestSpec(construct_id="NOPE")],
        aggregation_mode=AggregationMode.ARITHMETIC,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.FAILED
    assert "ConfigError" in (result.error or "")
    assert "NOPE" in (result.error or "")


def test_battery_runner_rejects_grey_only_against_black_box():
    register_plugin(GreyOnlyPlugin(construct_id="GREYONLY"))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[SubTestSpec(construct_id="GREYONLY")],
        aggregation_mode=AggregationMode.ARITHMETIC,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.FAILED
    assert "GREYONLY" in (result.error or "")


def test_battery_runner_rejects_weighted_without_weights():
    register_plugin(FixedScorePlugin(construct_id="A"))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[SubTestSpec(construct_id="A")],
        aggregation_mode=AggregationMode.WEIGHTED,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.FAILED
    assert "weighted" in (result.error or "").lower() or "weight" in (result.error or "").lower()


# ─── Happy path ────────────────────────────────────────────────────────


def test_battery_runner_arithmetic_runs_end_to_end():
    register_plugin(FixedScorePlugin(construct_id="A", score=50.0))
    register_plugin(FixedScorePlugin(construct_id="B", score=100.0))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[
            SubTestSpec(construct_id="A"),
            SubTestSpec(construct_id="B"),
        ],
        aggregation_mode=AggregationMode.ARITHMETIC,
        n_bootstrap=100,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.COMPLETED
    assert result.report is not None
    assert math.isclose(result.report.index_score, 75.0)
    assert len(result.sub_test_scores) == 2


def test_battery_runner_weighted_uses_weights():
    register_plugin(FixedScorePlugin(construct_id="A", score=50.0))
    register_plugin(FixedScorePlugin(construct_id="B", score=100.0))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[
            SubTestSpec(construct_id="A", weight=0.25),
            SubTestSpec(construct_id="B", weight=0.75),
        ],
        aggregation_mode=AggregationMode.WEIGHTED,
        n_bootstrap=100,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.COMPLETED
    assert result.report is not None
    assert math.isclose(result.report.index_score, 87.5)


# ─── Isolation: one sub-test failure does not kill the rest ─────────────


def test_battery_runner_isolates_bad_sub_test():
    """One sub-test's failure does not corrupt the others' results.

    The runner aggregates with ``expected_constructs`` set to every
    enabled sub-test, so an errored sub-test correctly fails the
    aggregation with :class:`IncompleteBatteryError`. The isolation
    guarantee is that the *good* sub-test still ran and its
    :class:`SubTestScore` is intact in the returned result, even
    though the aggregate is refused.
    """
    register_plugin(FixedScorePlugin(construct_id="GOOD", score=70.0))
    register_plugin(BoomPlugin(construct_id="BAD"))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[
            SubTestSpec(construct_id="GOOD"),
            SubTestSpec(construct_id="BAD"),
        ],
        aggregation_mode=AggregationMode.ARITHMETIC,
        n_bootstrap=50,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    # FAIL LOUDLY: the run as a whole is FAILED because the BAD
    # sub-test is expected and errored. The isolation property is
    # that both sub-test scores are still recorded individually.
    assert result.status == RunStatus.FAILED
    assert "IncompleteBatteryError" in (result.error or "")
    assert len(result.sub_test_scores) == 2
    good = next(s for s in result.sub_test_scores if s.construct_id == "GOOD")
    bad = next(s for s in result.sub_test_scores if s.construct_id == "BAD")
    assert good.error is None
    assert good.score == 70.0
    assert bad.error is not None
    assert "intentional failure" in bad.error


# ─── Timeout ───────────────────────────────────────────────────────────


def test_battery_runner_per_sub_test_timeout_fires():
    register_plugin(SlowPlugin(construct_id="SLOW"))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[SubTestSpec(construct_id="SLOW")],
        aggregation_mode=AggregationMode.ARITHMETIC,
        per_sub_test_timeout_s=0.2,
        n_bootstrap=50,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    # The slow plugin times out; the captured SubTestScore carries the
    # timeout error.
    assert len(result.sub_test_scores) == 1
    assert "per-sub-test timeout" in (result.sub_test_scores[0].error or "")


# ─── JSONL sink ────────────────────────────────────────────────────────


def test_battery_runner_writes_jsonl_records(tmp_path):
    register_plugin(FixedScorePlugin(construct_id="A", score=60.0, n_items=2))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[SubTestSpec(construct_id="A")],
        aggregation_mode=AggregationMode.ARITHMETIC,
        n_bootstrap=50,
    )
    jsonl_path = str(tmp_path / "out.jsonl")
    sink = JSONLSink(path=jsonl_path)
    runner = BatteryRunner(
        config=cfg, adapter=EchoAdapter(), jsonl_sink=sink
    )
    result = runner.run()
    assert result.status == RunStatus.COMPLETED
    with open(jsonl_path) as fh:
        lines = [json.loads(line) for line in fh if line.strip()]
    assert any(line["type"] == "sub_test_score" for line in lines)
    assert any(line["type"] == "response_record" for line in lines)


# ─── Parallel execution ───────────────────────────────────────────────


def test_battery_runner_parallel_executes_all():
    register_plugin(FixedScorePlugin(construct_id="P1", score=10.0))
    register_plugin(FixedScorePlugin(construct_id="P2", score=20.0))
    register_plugin(FixedScorePlugin(construct_id="P3", score=30.0))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[
            SubTestSpec(construct_id="P1"),
            SubTestSpec(construct_id="P2"),
            SubTestSpec(construct_id="P3"),
        ],
        aggregation_mode=AggregationMode.ARITHMETIC,
        parallelism=3,
        n_bootstrap=50,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    result = runner.run()
    assert result.status == RunStatus.COMPLETED
    assert math.isclose(result.report.index_score, 20.0)


# ─── Environment metadata ─────────────────────────────────────────────


def test_environment_metadata_contains_python_and_pid():
    md = _environment_metadata()
    assert "python_version" in md
    assert md["pid"] == os.getpid()
    assert "hostname" in md


# ─── Stop signal ─────────────────────────────────────────────────────


def test_battery_runner_request_stop_paused(tmp_path):
    register_plugin(FixedScorePlugin(construct_id="P1", score=10.0))
    register_plugin(FixedScorePlugin(construct_id="P2", score=20.0))
    cfg = BatteryConfig(
        target="t",
        adapter_name="echo",
        sub_tests=[
            SubTestSpec(construct_id="P1"),
            SubTestSpec(construct_id="P2"),
        ],
        aggregation_mode=AggregationMode.ARITHMETIC,
        n_bootstrap=50,
    )
    runner = BatteryRunner(config=cfg, adapter=EchoAdapter())
    runner.request_stop()
    result = runner.run()
    # request_stop before run means the first iteration sees the event
    # and bypasses every sub-test; the result must therefore land in
    # PAUSED (sequential path) with no completed sub-tests.
    assert result.status == RunStatus.PAUSED
    assert result.report is None
