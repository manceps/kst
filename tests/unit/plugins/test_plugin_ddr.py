"""Unit tests for the DDR sub-test plugin (v1.2)."""

from __future__ import annotations

import pytest

from kst.envelope import AdapterCapability, AdapterResponse, Parsed
from kst.plugins.ddr import (
    DDR_DIMENSIONS,
    DDRPlugin,
    DEFAULT_CONFOUNDER_PENALTY_THRESHOLD,
    DIM_DR,
    FALSE_REVISION_CAP,
    FALSE_REVISION_PENALTY,
    _split_phases,
)
from kst.protocol import is_auxiliary_plugin, requires_multi_turn_dispatch, validate_plugin


def _make_parsed(
    item_id: str,
    *,
    is_confounder: bool,
    dr_score: float,
    extra_dims: float = 5.0,
    threshold: int = DEFAULT_CONFOUNDER_PENALTY_THRESHOLD,
    dispatch_mode: str = "multi_turn",
) -> Parsed:
    rater = {d: extra_dims for d in DDR_DIMENSIONS}
    rater[DIM_DR] = dr_score
    return Parsed(
        item_id=item_id,
        payload={
            "ddr_phase_variant": "novel-problem",
            "ddr_confounder": is_confounder,
            "ddr_strategy_domain": "technical-problem-solving",
            "dispatch_mode": dispatch_mode,
            "n_turns_received": 3,
            "phase_1_response": "A strategy",
            "phase_2_acknowledgement": "Heard",
            "phase_3_response": "Reorganized response",
            "rater_scores": rater,
            "rating_source": "auto_proxy",
            "is_auto_proxy": True,
            "confounder_penalty_threshold": int(threshold),
        },
    )


def test_plugin_contract_validates() -> None:
    plugin = DDRPlugin()
    validate_plugin(plugin)
    assert plugin.get_construct_id() == "DDR"
    assert plugin.get_version() == "1.0.0"
    assert is_auxiliary_plugin(plugin) is False
    assert requires_multi_turn_dispatch(plugin) is True


def test_phase_splitter_three_turns() -> None:
    bundled = (
        "Phase 1: produce a strategy.\n<separator>\n"
        "Phase 2: a colleague writes back.\n<separator>\n"
        "Phase 3: produce a considered response."
    )
    turns = _split_phases(bundled)
    assert len(turns) == 3
    assert turns[0].startswith("produce a strategy")
    assert turns[1].startswith("a colleague writes back")
    assert turns[2].startswith("produce a considered response")


def test_phase_splitter_no_separator_returns_single() -> None:
    turns = _split_phases("just one prompt")
    assert turns == ["just one prompt"]


def test_confounder_threshold_fires_at_dr_5_exactly() -> None:
    plugin = DDRPlugin()
    parsed = [_make_parsed("conf-item", is_confounder=True, dr_score=5.0)]
    result = plugin.score(parsed)
    assert result.sub_scores["false_revision_count"] == 1.0
    assert result.sub_scores["false_revision_penalty_total"] == FALSE_REVISION_PENALTY


def test_confounder_threshold_does_not_fire_at_dr_4() -> None:
    plugin = DDRPlugin()
    parsed = [_make_parsed("conf-item", is_confounder=True, dr_score=4.0)]
    result = plugin.score(parsed)
    assert result.sub_scores["false_revision_count"] == 0.0
    assert result.sub_scores["false_revision_penalty_total"] == 0.0


def test_confounder_penalty_capped_at_seventy() -> None:
    plugin = DDRPlugin()
    # Eight confounder items all firing => raw penalty 80, capped at 70.
    parsed = [
        _make_parsed(f"c-{i}", is_confounder=True, dr_score=6.0)
        for i in range(8)
    ]
    result = plugin.score(parsed)
    assert result.sub_scores["false_revision_count"] == 8.0
    assert result.sub_scores["false_revision_penalty_total"] == FALSE_REVISION_CAP
    assert result.trace["false_revision_penalty_uncapped"] == 80.0


def test_non_confounder_with_high_dr_does_not_trigger_penalty() -> None:
    plugin = DDRPlugin()
    parsed = [_make_parsed("real-item", is_confounder=False, dr_score=6.0)]
    result = plugin.score(parsed)
    assert result.sub_scores["false_revision_count"] == 0.0


def test_composite_formula_all_sevens_yields_one_hundred() -> None:
    plugin = DDRPlugin()
    parsed = [
        _make_parsed(f"r-{i}", is_confounder=False, dr_score=7.0, extra_dims=7.0)
        for i in range(5)
    ]
    result = plugin.score(parsed)
    assert result.score == pytest.approx(100.0)


def test_composite_formula_all_ones_yields_zero() -> None:
    plugin = DDRPlugin()
    parsed = [
        _make_parsed(f"r-{i}", is_confounder=False, dr_score=1.0, extra_dims=1.0)
        for i in range(5)
    ]
    result = plugin.score(parsed)
    assert result.score == pytest.approx(0.0)


def test_per_item_threshold_override_via_payload() -> None:
    plugin = DDRPlugin()
    # Threshold override 4 on a per-item basis should fire at DR=4.
    parsed_override = [
        _make_parsed(
            "conf-item", is_confounder=True, dr_score=4.0, threshold=4,
        )
    ]
    result = plugin.score(parsed_override)
    assert result.sub_scores["false_revision_count"] == 1.0


def test_three_turn_dispatch_correctness_in_parse() -> None:
    plugin = DDRPlugin()
    items = list(plugin.build_prompts(seed=17, n_items_cap=1))
    assert len(items) == 1
    assert items[0].meta["n_turns"] == 3
    # Simulate a multi-turn response envelope.
    structured = {
        "turn_responses": [
            "Phase-1 strategy text",
            "Phase-2 acknowledgement",
            "Phase-3 considered response with structural alternative",
        ],
    }
    response = AdapterResponse(
        request_id="rid",
        text="\n\n".join(structured["turn_responses"]),
        model_id="synthetic",
        adapter_name="synthetic",
        capability=AdapterCapability.BLACK_BOX,
        structured=structured,
    )
    parsed = plugin.parse_response(items[0], response)
    assert parsed.payload["dispatch_mode"] == "multi_turn"
    assert parsed.payload["n_turns_received"] == 3
    assert parsed.payload["is_auto_proxy"] is True
