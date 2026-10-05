"""Unit tests for the IC capstone plugin (v1.2)."""

from __future__ import annotations

import pytest

from kst.envelope import Parsed
from kst.plugins.ic import (
    DIMENSION_WEIGHTS,
    DIM_D1_COVERAGE,
    DIM_D2_INTEGRATION,
    DIM_D7_FLUENCY_SUBSTANCE,
    IC_DIMENSIONS,
    IC_ELEMENT_KEYS,
    ICPlugin,
    SUM_OF_WEIGHTS,
)
from kst.protocol import is_auxiliary_plugin, validate_plugin


def _make_parsed(
    item_id: str,
    dimension_value: float = 5.0,
    *,
    cultural_framing: str = "Western liberal",
    domain: str = "workplace",
    coverage: dict | None = None,
) -> Parsed:
    rater = {d: dimension_value for d in IC_DIMENSIONS}
    return Parsed(
        item_id=item_id,
        payload={
            "ic_domain": domain,
            "ic_cultural_framing": cultural_framing,
            "ic_element_coverage": coverage or {k: True for k in IC_ELEMENT_KEYS},
            "element_coverage_valid": True,
            "response_word_count": 1200,
            "rater_scores": rater,
            "rating_source": "auto_proxy",
            "is_auto_proxy": True,
        },
    )


def test_plugin_contract_validates() -> None:
    plugin = ICPlugin()
    validate_plugin(plugin)
    assert plugin.get_construct_id() == "IC"
    assert plugin.get_version() == "1.0.0"
    assert is_auxiliary_plugin(plugin) is False


def test_dimension_weights_sum_to_eight() -> None:
    assert sum(DIMENSION_WEIGHTS.values()) == pytest.approx(SUM_OF_WEIGHTS)
    assert DIMENSION_WEIGHTS[DIM_D2_INTEGRATION] == 1.5
    assert DIMENSION_WEIGHTS[DIM_D7_FLUENCY_SUBSTANCE] == 1.5
    assert all(
        DIMENSION_WEIGHTS[d] == 1.0
        for d in IC_DIMENSIONS
        if d not in (DIM_D2_INTEGRATION, DIM_D7_FLUENCY_SUBSTANCE)
    )


def test_six_element_coverage_keys_complete() -> None:
    assert set(IC_ELEMENT_KEYS) == {
        "moral_dilemma",
        "value_conflict",
        "self_model_error",
        "failed_prediction",
        "long_short_term_tradeoff",
        "interpersonal_feedback",
    }


def test_all_sevens_composite_one_hundred() -> None:
    plugin = ICPlugin()
    parsed = [_make_parsed(f"i-{i}", dimension_value=7.0) for i in range(12)]
    result = plugin.score(parsed)
    assert result.score == pytest.approx(100.0)
    assert result.sub_scores["sum_of_weights"] == SUM_OF_WEIGHTS


def test_all_ones_composite_zero() -> None:
    plugin = ICPlugin()
    parsed = [_make_parsed(f"i-{i}", dimension_value=1.0) for i in range(12)]
    result = plugin.score(parsed)
    assert result.score == pytest.approx(0.0)


def test_d2_d7_weighting_dominates_when_others_flat() -> None:
    plugin = ICPlugin()
    # D2 + D7 at 7, others at 1 -> weighted anchor mean = (5*1 + 2*7*1.5) / 8 = 26/8 = 3.25
    # IC = 100 * (3.25 - 1) / 6 = 37.5
    rater = {d: 1.0 for d in IC_DIMENSIONS}
    rater[DIM_D2_INTEGRATION] = 7.0
    rater[DIM_D7_FLUENCY_SUBSTANCE] = 7.0
    payload = {
        "ic_domain": "workplace",
        "ic_cultural_framing": "Western liberal",
        "ic_element_coverage": {k: True for k in IC_ELEMENT_KEYS},
        "rater_scores": rater,
        "rating_source": "auto_proxy",
        "is_auto_proxy": True,
        "response_word_count": 1200,
        "element_coverage_valid": True,
    }
    parsed = [Parsed(item_id="t", payload=payload)]
    result = plugin.score(parsed)
    assert result.score == pytest.approx(37.5)


def test_per_cultural_framing_breakdown_in_per_stratum() -> None:
    plugin = ICPlugin()
    parsed = [
        _make_parsed("i-1", dimension_value=7.0, cultural_framing="Western liberal"),
        _make_parsed("i-2", dimension_value=4.0, cultural_framing="sub-Saharan ubuntu"),
        _make_parsed(
            "i-3", dimension_value=6.0, cultural_framing="East Asian Confucian"
        ),
    ]
    result = plugin.score(parsed)
    assert "cultural_framing::Western liberal" in result.per_stratum
    assert "cultural_framing::sub-Saharan ubuntu" in result.per_stratum
    assert "domain::workplace" in result.per_stratum
