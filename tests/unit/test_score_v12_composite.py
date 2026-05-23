"""Unit tests for the v1.2 composite + v1.0-comparable bracket + HRO multiplier."""

from __future__ import annotations

import math

import pytest

from kst.envelope import ScoreInterval, SubTestScore
from kst.score import (
    AUXILIARY_CONSTRUCTS_V12,
    PRIMARY_CONSTRUCTS_V12,
    V10_COMPARABLE_WEIGHTS,
    V12_COMPOSITE_WEIGHTS,
    aggregate_v12_score_report,
    compute_v1_0_comparable_composite,
    split_primary_and_auxiliary,
)


def _make(construct: str, score: float, *, trace=None) -> SubTestScore:
    return SubTestScore(
        test_id=construct,
        test_name=construct,
        construct_id=construct,
        version="1.0",
        score=float(score),
        max_score=100.0,
        trace=trace or {},
    )


def test_v12_weights_sum_to_one() -> None:
    assert sum(V12_COMPOSITE_WEIGHTS.values()) == pytest.approx(1.0)
    assert V12_COMPOSITE_WEIGHTS["KMR-Adv"] == 0.18
    assert V12_COMPOSITE_WEIGHTS["DDR"] == 0.10
    assert V12_COMPOSITE_WEIGHTS["IC"] == 0.08


def test_v10_comparable_weights_sum_to_one_and_preserve_ratios() -> None:
    assert sum(V10_COMPARABLE_WEIGHTS.values()) == pytest.approx(1.0)
    # Architecture spec sec 12: KMR-Adv / ROT-5 / BWD get 0.18/0.82,
    # APE-A / HRO get 0.14/0.82.
    assert V10_COMPARABLE_WEIGHTS["KMR-Adv"] == pytest.approx(0.18 / 0.82)
    assert V10_COMPARABLE_WEIGHTS["APE-A"] == pytest.approx(0.14 / 0.82)


def test_v10_comparable_composite_matches_pure_v10_at_high_hro() -> None:
    # All sub-tests at 80, HRO at 80 (multiplier 1.0).
    scores = [_make(c, 80.0) for c in V10_COMPARABLE_WEIGHTS]
    composite = compute_v1_0_comparable_composite(scores)
    assert composite == pytest.approx(80.0)


def test_v10_comparable_composite_with_hro_multiplier() -> None:
    # All sub-tests at 60, HRO at 60 -> multiplier = 0.5 + 0.5 * (60-25)/50 = 0.85
    scores = [_make(c, 60.0) for c in V10_COMPARABLE_WEIGHTS]
    composite = compute_v1_0_comparable_composite(scores)
    assert composite == pytest.approx(60.0 * 0.85)


def test_v10_comparable_returns_none_when_missing_sub_test() -> None:
    # Drop HRO.
    scores = [
        _make(c, 70.0)
        for c in V10_COMPARABLE_WEIGHTS
        if c != "HRO"
    ]
    composite = compute_v1_0_comparable_composite(scores)
    assert composite is None


def test_split_primary_and_auxiliary_routes_sdt_mot() -> None:
    primary_scores = [_make(c, 50.0) for c in PRIMARY_CONSTRUCTS_V12]
    aux = _make(AUXILIARY_CONSTRUCTS_V12[0], 45.0, trace={"is_auxiliary": True})
    primary, auxiliary = split_primary_and_auxiliary(primary_scores + [aux])
    assert len(primary) == 7
    assert len(auxiliary) == 1
    assert auxiliary[0].construct_id == "SDT-MOT"


def test_v12_composite_with_seven_primaries_at_eighty() -> None:
    scores = [_make(c, 80.0) for c in PRIMARY_CONSTRUCTS_V12]
    report = aggregate_v12_score_report(
        scores,
        target="unit-test",
        adapter_name="synthetic",
        capability="black_box",
        n_bootstrap=0,
    )
    assert report.index_score == pytest.approx(80.0)
    assert report.v1_0_composite == pytest.approx(80.0)
    assert report.auxiliary_reports == []


def test_v12_composite_attaches_auxiliary_bracket() -> None:
    scores = [_make(c, 70.0) for c in PRIMARY_CONSTRUCTS_V12]
    aux = _make("SDT-MOT", 62.5, trace={"is_auxiliary": True})
    aux.sub_scores = {"composite_directional_gap": 1.0}
    report = aggregate_v12_score_report(
        scores + [aux],
        target="unit-test",
        adapter_name="synthetic",
        capability="black_box",
        n_bootstrap=0,
    )
    assert len(report.auxiliary_reports) == 1
    aux_entry = report.auxiliary_reports[0]
    assert aux_entry.construct_id == "SDT-MOT"
    assert aux_entry.descriptive_score == pytest.approx(62.5)


def test_hro_multiplier_preserved_in_v12_aggregate() -> None:
    # HRO at 50 -> multiplier 0.5 + 0.5*(50-25)/50 = 0.75; others at 80.
    scores = [_make(c, 80.0 if c != "HRO" else 50.0) for c in PRIMARY_CONSTRUCTS_V12]
    report = aggregate_v12_score_report(
        scores,
        target="unit-test",
        adapter_name="synthetic",
        capability="black_box",
        n_bootstrap=0,
    )
    # Raw composite = 0.86 * 80 + 0.14 * 50 = 68.80 + 7.00 = 75.80
    # Multiplier on HRO=50: 0.75. Corrected = 75.80 * 0.75 = 56.85
    assert report.raw_index_score == pytest.approx(75.80, rel=1e-3)
    assert report.index_score == pytest.approx(56.85, rel=1e-3)
    assert report.hro_integrity is not None
    assert report.hro_integrity.multiplier == pytest.approx(0.75, rel=1e-3)


def test_v12_aggregate_pinned_v1_0_run_score_matches_v10_aggregator() -> None:
    """Back-compat: a v1.0-equivalent run (5 sub-tests only) computed
    through aggregate_v12_score_report.v1_0_composite must match a
    direct compute_v1_0_comparable_composite on the same inputs.
    """
    scores_v10 = [_make(c, 72.0) for c in V10_COMPARABLE_WEIGHTS]
    direct = compute_v1_0_comparable_composite(scores_v10)
    via_aggregator = aggregate_v12_score_report(
        scores_v10,
        target="back-compat",
        adapter_name="synthetic",
        capability="black_box",
        n_bootstrap=0,
    ).v1_0_composite
    assert direct == pytest.approx(via_aggregator)
