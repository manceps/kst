"""Unit tests for kst.score.

Covers each aggregation mode, weight validation, bootstrap CI shape,
Krippendorff alpha edge cases, DIF detection, and IncompleteBatteryError
fail-loud behavior.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import math

import pytest

from kst.envelope import ScoreInterval, SubTestScore
from kst.errors import (
    ConfigError,
    IncompleteBatteryError,
    ScoreValidationError,
)
from kst.score import (
    AggregationMode,
    aggregate_score_report,
    aggregate_scores,
    bootstrap_ci,
    differential_item_functioning,
    krippendorff_alpha_interval,
)


# ─── Aggregation modes ──────────────────────────────────────────────────


def test_arithmetic_mode_simple():
    assert aggregate_scores([10.0, 20.0, 30.0], AggregationMode.ARITHMETIC) == 20.0


def test_geometric_mode_simple():
    val = aggregate_scores([10.0, 40.0], AggregationMode.GEOMETRIC)
    assert math.isclose(val, math.sqrt(400.0))


def test_geometric_mode_zero_collapses_to_zero():
    assert (
        aggregate_scores([0.0, 50.0, 100.0], AggregationMode.GEOMETRIC) == 0.0
    )


def test_min_mode():
    assert aggregate_scores([100.0, 25.0, 75.0], AggregationMode.MIN) == 25.0


def test_weighted_mode_validates_sum():
    val = aggregate_scores(
        [50.0, 100.0], AggregationMode.WEIGHTED, weights=[0.4, 0.6]
    )
    assert math.isclose(val, 80.0)


def test_weighted_requires_weights_argument():
    with pytest.raises(ConfigError):
        aggregate_scores([50.0], AggregationMode.WEIGHTED)


def test_weighted_rejects_unaligned_weights():
    with pytest.raises(ConfigError):
        aggregate_scores(
            [50.0, 50.0], AggregationMode.WEIGHTED, weights=[1.0]
        )


def test_weighted_rejects_negative_weights():
    with pytest.raises(ConfigError):
        aggregate_scores(
            [50.0, 50.0], AggregationMode.WEIGHTED, weights=[-0.1, 1.1]
        )


def test_weighted_rejects_unnormalized_weights():
    with pytest.raises(ConfigError):
        aggregate_scores(
            [50.0, 50.0], AggregationMode.WEIGHTED, weights=[0.6, 0.6]
        )


def test_validate_rejects_out_of_range_score():
    with pytest.raises(ScoreValidationError):
        aggregate_scores([101.0], AggregationMode.ARITHMETIC)


def test_validate_rejects_nan_score():
    with pytest.raises(ScoreValidationError):
        aggregate_scores([float("nan")], AggregationMode.ARITHMETIC)


def test_aggregate_scores_unknown_mode_raises():
    with pytest.raises(ConfigError):
        aggregate_scores([10.0], "not-a-mode")  # type: ignore[arg-type]


def test_aggregate_scores_empty_raises():
    with pytest.raises(ConfigError):
        aggregate_scores([])


# ─── Bootstrap CI ───────────────────────────────────────────────────────


def test_bootstrap_ci_returns_score_interval():
    ci = bootstrap_ci([10, 20, 30, 40, 50], n_bootstrap=500, seed=1)
    assert isinstance(ci, ScoreInterval)
    assert ci.lower <= ci.upper
    assert 0.0 <= ci.lower <= 50.0
    assert 0.0 <= ci.upper <= 50.0
    assert ci.confidence == 0.95
    assert ci.n_bootstrap == 500


def test_bootstrap_ci_supports_median():
    ci = bootstrap_ci(
        [1, 2, 3, 4, 5], n_bootstrap=200, seed=1, statistic="median"
    )
    assert 1 <= ci.lower <= 5
    assert 1 <= ci.upper <= 5


def test_bootstrap_ci_supports_min_and_geomean():
    ci_min = bootstrap_ci([1, 2, 3], n_bootstrap=100, seed=1, statistic="min")
    assert ci_min.lower == 1
    ci_gm = bootstrap_ci(
        [10, 20, 40], n_bootstrap=100, seed=1, statistic="geomean"
    )
    assert ci_gm.lower > 0


def test_bootstrap_ci_rejects_bad_confidence():
    with pytest.raises(ConfigError):
        bootstrap_ci([1, 2, 3], confidence=1.5)


def test_bootstrap_ci_rejects_empty_samples():
    with pytest.raises(ConfigError):
        bootstrap_ci([])


def test_bootstrap_ci_rejects_bad_statistic():
    with pytest.raises(ConfigError):
        bootstrap_ci([1, 2, 3], statistic="hyperbolic")  # type: ignore[arg-type]


def test_bootstrap_ci_rejects_bad_n_bootstrap():
    with pytest.raises(ConfigError):
        bootstrap_ci([1, 2, 3], n_bootstrap=0)


# ─── Krippendorff alpha ─────────────────────────────────────────────────


def test_krippendorff_alpha_perfect_agreement():
    data = [[5, 5, 5], [3, 3, 3], [1, 1, 1]]
    assert krippendorff_alpha_interval(data) == 1.0


def test_krippendorff_alpha_systematic_disagreement_returns_low_value():
    data = [[1, 5], [1, 5], [1, 5]]
    alpha = krippendorff_alpha_interval(data)
    # Systematic disagreement (raters consistently disagree by 4)
    # produces alpha far below 1.0.
    assert alpha < 0.5


def test_krippendorff_alpha_empty_raises():
    with pytest.raises(ConfigError):
        krippendorff_alpha_interval([])


def test_krippendorff_alpha_handles_missing_with_nan():
    data = [[1.0, float("nan"), 1.0], [2.0, 2.0, 2.0]]
    alpha = krippendorff_alpha_interval(data)
    assert isinstance(alpha, float)


# ─── DIF ────────────────────────────────────────────────────────────────


def test_dif_flags_items_above_threshold():
    per_target = {
        "openai": [80.0, 60.0, 90.0],
        "caici":  [40.0, 65.0, 95.0],
    }
    result = differential_item_functioning(per_target, threshold=0.30)
    assert result["n_items"] == 3
    # Item 0 spread = 0.40 -> flagged.
    assert 0 in result["flagged_items"]
    # Item 1 spread = 0.05 -> not flagged.
    assert 1 not in result["flagged_items"]


def test_dif_empty_returns_zero_flagged():
    result = differential_item_functioning({})
    assert result["n_flagged"] == 0
    assert result["n_items"] == 0


def test_dif_rejects_unequal_length_vectors():
    with pytest.raises(ConfigError):
        differential_item_functioning(
            {"a": [1.0, 2.0], "b": [3.0]}
        )


# ─── aggregate_score_report end-to-end ──────────────────────────────────


def _mk_score(cid: str, version: str = "1.0", normalized: float = 50.0) -> SubTestScore:
    return SubTestScore(
        test_id=cid,
        test_name=cid,
        construct_id=cid,
        version=version,
        score=normalized,
        max_score=100.0,
    )


def test_aggregate_score_report_weighted_succeeds():
    scores = [_mk_score("A", normalized=50.0), _mk_score("B", normalized=100.0)]
    rep = aggregate_score_report(
        scores,
        target="caici",
        adapter_name="caici",
        capability="grey_box",
        mode=AggregationMode.WEIGHTED,
        weights={"A": 0.5, "B": 0.5},
        expected_constructs=["A", "B"],
        n_bootstrap=100,
        seed=7,
    )
    assert math.isclose(rep.index_score, 75.0)
    assert rep.aggregation_mode == AggregationMode.WEIGHTED
    assert rep.index_ci is not None
    assert len(rep.sub_tests) == 2


def test_aggregate_score_report_raises_on_missing_construct():
    scores = [_mk_score("A")]
    with pytest.raises(IncompleteBatteryError) as exc_info:
        aggregate_score_report(
            scores,
            target="x",
            adapter_name="x",
            capability="black_box",
            mode=AggregationMode.ARITHMETIC,
            expected_constructs=["A", "B", "C"],
        )
    err = exc_info.value
    assert err.expected == 3
    assert err.actual == 1
    assert err.missing == ["B", "C"]


def test_aggregate_score_report_skips_errored_subtests_in_completeness_check():
    s1 = _mk_score("A")
    s2 = _mk_score("B")
    s2.error = "boom"
    with pytest.raises(IncompleteBatteryError):
        aggregate_score_report(
            [s1, s2],
            target="x",
            adapter_name="x",
            capability="black_box",
            mode=AggregationMode.ARITHMETIC,
            expected_constructs=["A", "B"],
        )


def test_aggregate_score_report_weighted_missing_weight_raises():
    scores = [_mk_score("A"), _mk_score("B")]
    with pytest.raises(ConfigError):
        aggregate_score_report(
            scores,
            target="x",
            adapter_name="x",
            capability="black_box",
            mode=AggregationMode.WEIGHTED,
            weights={"A": 1.0},  # missing B
        )


def test_aggregate_score_report_seed_replications_alpha():
    scores = [_mk_score("A"), _mk_score("B"), _mk_score("C")]
    rep = aggregate_score_report(
        scores,
        target="x",
        adapter_name="x",
        capability="black_box",
        mode=AggregationMode.ARITHMETIC,
        seed_replications={
            "seed_1": [50.0, 60.0, 70.0],
            "seed_2": [51.0, 61.0, 71.0],
        },
        n_bootstrap=100,
        seed=42,
    )
    assert rep.reproducibility_alpha is not None


def test_aggregate_score_report_dif_payload_attached():
    scores = [_mk_score("A"), _mk_score("B")]
    rep = aggregate_score_report(
        scores,
        target="x",
        adapter_name="x",
        capability="black_box",
        mode=AggregationMode.ARITHMETIC,
        dif_per_target={
            "openai": [80.0, 30.0],
            "caici": [70.0, 90.0],
        },
        n_bootstrap=100,
    )
    assert rep.dif is not None
    assert rep.dif["n_items"] == 2
