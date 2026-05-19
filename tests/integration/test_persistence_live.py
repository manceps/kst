"""Live integration test: KSTPersistence against the dev PostgreSQL.

Exercises schema bootstrap, write paths for every STT table, and the
canonical read paths. Skipped when the dev posture is not present
(no ``CAICI_DB_*`` envs, or proxy not reachable on the resolved
host:port).

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import os
import socket
import uuid

import pytest

from kst.adapters.base import BaseAdapter
from kst.envelope import (
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    GreyBoxTelemetry,
    Item,
    RunStatus,
    ScoreInterval,
    SubTestScore,
)
from kst.persistence import KSTPersistence
from kst.score import (
    AggregationMode,
    aggregate_score_report,
)


def _db_reachable() -> bool:
    host = os.environ.get("CAICI_DB_HOST", "127.0.0.1")
    port = int(os.environ.get("CAICI_DB_PORT", "5432"))
    try:
        sock = socket.create_connection((host, port), timeout=2.0)
        sock.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_reachable(),
    reason="PostgreSQL not reachable (no proxy and no local server).",
)


@pytest.fixture(scope="module")
def persistence():
    p = KSTPersistence()
    yield p
    p.close()


def test_persistence_create_run_and_read_back(persistence):
    rid = persistence.create_run(
        target="caici",
        adapter_name="caici",
        capability=AdapterCapability.GREY_BOX,
        aggregation_mode=AggregationMode.WEIGHTED.value,
        weights={"A": 0.5, "B": 0.5},
        expected_constructs=["A", "B"],
        environment={"test": True},
        notes="integration_test",
    )
    run = persistence.get_run(rid)
    assert run is not None
    assert run["target"] == "caici"
    assert run["status"] == RunStatus.PENDING.value
    persistence.mark_running(rid)
    run = persistence.get_run(rid)
    assert run["status"] == RunStatus.RUNNING.value


def test_persistence_insert_sub_test_and_response_and_aggregate(persistence):
    rid = persistence.create_run(
        target="caici",
        adapter_name="caici",
        capability=AdapterCapability.GREY_BOX,
        aggregation_mode=AggregationMode.ARITHMETIC.value,
        weights={},
        expected_constructs=["A"],
        environment={"test": True},
        notes="integration_test_full_cycle",
    )
    persistence.mark_running(rid)

    sub = SubTestScore(
        test_id="A",
        test_name="Test A",
        construct_id="A",
        version="1.0",
        score=72.5,
        max_score=100.0,
        n_items=2,
        n_parse_errors=0,
        ci=ScoreInterval(lower=70.0, upper=75.0, confidence=0.95, n_bootstrap=200),
        duration_s=1.5,
        sub_scores={"alpha": 0.7, "beta": 0.8},
        per_stratum={"easy": 80.0, "hard": 60.0},
        trace={"items": 2},
    )
    persistence.insert_sub_test_result(rid, sub)
    persistence.mark_construct_completed(rid, "A")

    req = AdapterRequest(
        prompt="What is 2+2?",
        construct_id="A",
        item_id="i_0",
        sub_test_version="1.0",
    )
    item = Item(item_id="i_0", prompt=req.prompt)
    resp = AdapterResponse(
        request_id=req.request_id,
        text="4",
        model_id="CAI.CI-test",
        adapter_name="caici",
        capability=AdapterCapability.GREY_BOX,
        status_code=200,
        latency_s=0.42,
        attempts=1,
        grey_box_telemetry=GreyBoxTelemetry(
            epistemic_state="know",
            confidence=0.95,
            competence=0.99,
            raw={"sample": True},
        ),
        raw={"choices": [{"message": {"content": "4"}}]},
    )
    persistence.insert_response_record(rid, "A", "1.0", item, req, resp)

    # Read back the sub_test row.
    rows = persistence.get_sub_test_results(rid)
    assert len(rows) == 1
    assert rows[0]["construct_id"] == "A"
    assert abs(rows[0]["normalized"] - 72.5) < 1e-6
    # Read back the response record.
    rec = persistence.get_response_records(rid)
    assert len(rec) == 1
    assert rec[0]["response_text"] == "4"

    # Aggregate report.
    report = aggregate_score_report(
        [sub],
        target="caici",
        adapter_name="caici",
        capability="grey_box",
        run_id=rid,
        mode=AggregationMode.ARITHMETIC,
        expected_constructs=["A"],
        environment={"test": True},
        n_bootstrap=50,
        seed=1,
    )
    persistence.upsert_score_aggregate(report)
    persistence.mark_completed(rid)
    agg = persistence.get_score_aggregate(rid)
    assert agg is not None
    assert abs(agg["index_score"] - 72.5) < 1e-6
    run = persistence.get_run(rid)
    assert run["status"] == RunStatus.COMPLETED.value


def test_persistence_list_and_compare(persistence):
    rid1 = persistence.create_run(
        target="integration_compare_target",
        adapter_name="echo",
        capability=AdapterCapability.BLACK_BOX,
        aggregation_mode="arithmetic",
        weights={},
        expected_constructs=["X"],
        environment={},
        notes="compare_test_a",
    )
    rid2 = persistence.create_run(
        target="integration_compare_target",
        adapter_name="echo",
        capability=AdapterCapability.BLACK_BOX,
        aggregation_mode="arithmetic",
        weights={},
        expected_constructs=["X"],
        environment={},
        notes="compare_test_b",
    )
    rows = persistence.list_runs(target="integration_compare_target", limit=10)
    found = {r["run_id"] for r in rows}
    assert rid1 in found
    assert rid2 in found
    comparison = persistence.compare_runs([rid1, rid2])
    assert rid1 in comparison
    assert rid2 in comparison
