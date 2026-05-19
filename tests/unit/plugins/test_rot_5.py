"""Unit tests for kst.plugins.rot_5 (ROT-5)."""

from __future__ import annotations

from typing import List

import pytest

from kst.envelope import (
    AdapterCapability,
    AdapterResponse,
    ApplicabilityMode,
    GreyBoxTelemetry,
    Parsed,
    SubTestScore,
)
from kst.plugins.rot_5 import (
    ALL_VARIANTS,
    ROT5Plugin,
    VARIANT_ADVERSARIAL,
    VARIANT_PERTURBATION,
    VARIANT_SURFACE,
    _detect_confabulation,
    _grade_item,
    _has_confident_justification,
    _is_omniscient_collapse,
    _split_response,
)
from kst.protocol import validate_plugin


def _mk_response(text: str, *, telemetry: GreyBoxTelemetry = None) -> AdapterResponse:
    return AdapterResponse(
        request_id="r",
        text=text,
        model_id="test",
        adapter_name="test",
        capability=AdapterCapability.BLACK_BOX,
        status_code=200,
        grey_box_telemetry=telemetry,
    )


def test_plugin_satisfies_protocol():
    p = ROT5Plugin()
    validate_plugin(p)
    assert p.get_construct_id() == "ROT-5"
    assert p.get_version() == "1.0.0"
    assert p.applicability_modes == ApplicabilityMode.BOTH


def test_plugin_rejects_invalid_n_base_items():
    with pytest.raises(ValueError):
        ROT5Plugin(n_base_items=0)


def test_build_prompts_produces_three_variants():
    p = ROT5Plugin(n_base_items=4)
    items = list(p.build_prompts(seed=12))
    assert len(items) == 4 * len(ALL_VARIANTS)
    counts = {v: 0 for v in ALL_VARIANTS}
    for it in items:
        counts[it.meta["variant"]] += 1
    assert all(v == 4 for v in counts.values())


def test_build_prompts_seed_determinism():
    p = ROT5Plugin(n_base_items=3)
    a = [i.prompt for i in p.build_prompts(seed=99)]
    b = [i.prompt for i in p.build_prompts(seed=99)]
    c = [i.prompt for i in p.build_prompts(seed=42)]
    assert a == b
    assert a != c


def test_build_prompts_perturbation_renames_agents():
    p = ROT5Plugin(n_base_items=1)
    items = list(p.build_prompts(seed=5))
    surface = next(i for i in items if i.meta["variant"] == VARIANT_SURFACE)
    pert = next(i for i in items if i.meta["variant"] == VARIANT_PERTURBATION)
    assert set(surface.meta["agents"].values()) != set(pert.meta["agents"].values())


def test_build_prompts_adversarial_appends_confounder():
    p = ROT5Plugin(n_base_items=1)
    items = list(p.build_prompts(seed=8))
    surface = next(i for i in items if i.meta["variant"] == VARIANT_SURFACE)
    adv = next(i for i in items if i.meta["variant"] == VARIANT_ADVERSARIAL)
    assert len(adv.prompt) > len(surface.prompt)


def test_split_response_canonical():
    text = (
        "REASONING: trace one two three\n"
        "FINAL_ANSWER: believes P is true\n"
        "CERTAINTY: FIFTH_ORDER"
    )
    r, f, c = _split_response(text)
    assert "trace" in r
    assert "believes P is true" in f
    assert c == "FIFTH_ORDER"


def test_split_response_empty_returns_none():
    r, f, c = _split_response("")
    assert r is None and f is None and c is None


def test_grade_item_correct_fifth_order():
    score = _grade_item(
        final="X believes P is true",
        certainty="FIFTH_ORDER",
        full_text="...",
        correct="believes P is true",
        omniscient="believes P is false",
        fourth_order_safe="cannot determine",
    )
    assert score == 2


def test_grade_item_fourth_order_partial_credit():
    score = _grade_item(
        final="cannot determine",
        certainty="FOURTH_ORDER_HONEST",
        full_text="...",
        correct="believes P is true",
        omniscient="believes P is false",
        fourth_order_safe="cannot determine",
    )
    assert score == 1


def test_grade_item_omniscient_collapse_zero():
    score = _grade_item(
        final="believes P is false",
        certainty=None,
        full_text="REASONING: it's clear from the scene",
        correct="believes P is true",
        omniscient="believes P is false",
        fourth_order_safe="cannot determine",
    )
    assert score == 0


def test_grade_item_confabulation_minus_one():
    score = _grade_item(
        final="believes P is false",
        certainty="FIFTH_ORDER",
        full_text=(
            "REASONING: clearly, according to the document, the timeline shows..."
        ),
        correct="believes P is true",
        omniscient="believes P is false",
        fourth_order_safe="cannot determine",
    )
    assert score == -1


def test_grade_item_blank_final_is_zero():
    score = _grade_item(
        final=None,
        certainty=None,
        full_text="",
        correct="x",
        omniscient="y",
        fourth_order_safe="z",
    )
    assert score == 0


def test_detect_confabulation_negative():
    assert _detect_confabulation("ok", "FOURTH_ORDER_HONEST", 1) is False
    assert _detect_confabulation("ok", "UNCERTAIN", 0) is False


def test_detect_confabulation_positive_via_raw_score():
    assert _detect_confabulation("anything", None, -1) is True


def test_detect_confabulation_invents_fact():
    assert (
        _detect_confabulation(
            "REASONING: in 1987 the scene...",
            "FIFTH_ORDER",
            0,
        )
        is True
    )


def test_is_omniscient_collapse_positive():
    payload = {
        "final_answer": "Eve believes P is false",
        "omniscient_distractor": "believes P is false",
    }
    assert _is_omniscient_collapse(payload)


def test_is_omniscient_collapse_negative_when_blank():
    assert not _is_omniscient_collapse({"final_answer": None, "omniscient_distractor": None})


def test_has_confident_justification():
    assert _has_confident_justification(
        "clearly, according to the document, X is true"
    )
    assert not _has_confident_justification("possibly, X is true")
    assert not _has_confident_justification("")


def test_parse_response_records_missing_final_answer():
    p = ROT5Plugin(n_base_items=1)
    items = list(p.build_prompts(seed=1))
    parsed = p.parse_response(items[0], _mk_response("REASONING: only this"))
    assert parsed.error is not None


def test_parse_response_captures_telemetry():
    p = ROT5Plugin(n_base_items=1)
    items = list(p.build_prompts(seed=1))
    text = (
        "REASONING: ...\n"
        f"FINAL_ANSWER: {items[0].meta['correct_answer']}\n"
        "CERTAINTY: FIFTH_ORDER"
    )
    tele = GreyBoxTelemetry(workspace_selectivity=0.71)
    parsed = p.parse_response(items[0], _mk_response(text, telemetry=tele))
    assert parsed.payload["telemetry_workspace_selectivity"] == 0.71


def test_score_perfect_battery_caps_at_100():
    p = ROT5Plugin(n_base_items=3)
    items = list(p.build_prompts(seed=2))
    parsed: List[Parsed] = []
    for it in items:
        text = (
            "REASONING: ...\n"
            f"FINAL_ANSWER: {it.meta['correct_answer']}\n"
            "CERTAINTY: FIFTH_ORDER"
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    sc = p.score(parsed)
    assert sc.normalized == 100.0


def test_score_perturbation_bonus_applied():
    p = ROT5Plugin(n_base_items=3)
    items = list(p.build_prompts(seed=3))
    parsed: List[Parsed] = []
    for it in items:
        text = (
            "REASONING: ...\n"
            f"FINAL_ANSWER: {it.meta['correct_answer']}\n"
            "CERTAINTY: FIFTH_ORDER"
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    sc = p.score(parsed)
    # Both surface and perturbation should be near 100, gap small -> bonus.
    assert sc.sub_scores["stability_adjustment"] >= 0.0


def test_score_perturbation_penalty_applied_for_pattern_match():
    p = ROT5Plugin(n_base_items=3)
    items = list(p.build_prompts(seed=4))
    parsed: List[Parsed] = []
    for it in items:
        # Get surface right, perturbation wrong.
        if it.meta["variant"] == VARIANT_SURFACE:
            text = (
                "REASONING: ...\n"
                f"FINAL_ANSWER: {it.meta['correct_answer']}\n"
                "CERTAINTY: FIFTH_ORDER"
            )
        else:
            text = (
                "REASONING: ...\n"
                f"FINAL_ANSWER: {it.meta['omniscient_distractor']}\n"
                "CERTAINTY: FIFTH_ORDER"
            )
        parsed.append(p.parse_response(it, _mk_response(text)))
    sc = p.score(parsed)
    assert sc.sub_scores["perturbation_gap"] > 0.3
    assert sc.sub_scores["stability_adjustment"] < 0.0


def test_score_confabulation_caps():
    p = ROT5Plugin(
        n_base_items=12,
        confabulation_cap_threshold=2,
        confabulation_cap=50.0,
    )
    items = list(p.build_prompts(seed=5))
    parsed: List[Parsed] = []
    for it in items:
        # All confabulating: omniscient + confident justification.
        text = (
            "REASONING: clearly, according to the document, the timeline shows.\n"
            f"FINAL_ANSWER: {it.meta['omniscient_distractor']}\n"
            "CERTAINTY: FIFTH_ORDER"
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    sc = p.score(parsed)
    assert sc.sub_scores["confabulation_count"] > 2
    assert sc.normalized <= 50.0


def test_score_handles_parse_errors():
    p = ROT5Plugin(n_base_items=2)
    items = list(p.build_prompts(seed=6))
    parsed = [
        p.parse_response(it, _mk_response("nothing parseable"))
        for it in items
    ]
    sc = p.score(parsed)
    assert isinstance(sc, SubTestScore)
    assert sc.n_parse_errors == len(items)
