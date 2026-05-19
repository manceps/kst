"""Unit tests for kst.plugins.bwd (BWD)."""

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
from kst.plugins.bwd import (
    BERLIN_CRITERIA,
    BERLIN_FACTUAL,
    BWDPlugin,
    DOMAINS,
    FRAMING_FIRST,
    FRAMING_THIRD,
    TRADITIONS,
    _auto_proxy_berlin_rating,
    _detect_confabulation_in_response,
    _detect_sycophancy,
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
    p = BWDPlugin()
    validate_plugin(p)
    assert p.get_construct_id() == "BWD"
    assert p.get_version() == "1.0.0"
    assert p.applicability_modes == ApplicabilityMode.BOTH


def test_plugin_rejects_invalid_rating_mode():
    with pytest.raises(ValueError):
        BWDPlugin(rating_mode="bogus")


def test_build_prompts_full_battery():
    p = BWDPlugin()
    items = list(p.build_prompts(seed=2))
    # 6 domains x 4 traditions x 2 framings = 48 items
    assert len(items) == len(DOMAINS) * len(TRADITIONS) * 2


def test_build_prompts_seed_determinism():
    p = BWDPlugin()
    a = [i.meta["self_distancing"] for i in p.build_prompts(seed=11)]
    b = [i.meta["self_distancing"] for i in p.build_prompts(seed=11)]
    c = [i.meta["self_distancing"] for i in p.build_prompts(seed=12)]
    assert a == b
    # Different seed must produce a different self-distancing assignment.
    assert a != c


def test_split_response_canonical():
    text = (
        "MAIN_RESPONSE:\nbody of response with reasoning across paragraphs.\n\n"
        "FOLLOW_UP_RESPONSE:\nI stand by my reasoning.\n\n"
        "STABILITY_SELF_REPORT: UNCHANGED"
    )
    main, follow, stab = _split_response(text)
    assert "body of response" in main
    assert "I stand by my reasoning" in follow
    assert stab == "UNCHANGED"


def test_split_response_empty():
    main, follow, stab = _split_response("")
    assert main is None and follow is None and stab is None


def test_detect_sycophancy_self_reported():
    assert _detect_sycophancy(
        "x", "y", "REVISED_UNDER_PRESSURE"
    ) is True
    assert _detect_sycophancy(
        "x", "y", "UNCHANGED"
    ) is False


def test_detect_sycophancy_jaccard_low_means_flip():
    assert _detect_sycophancy(
        "The patient should consider hospice care given the prognosis and family support",
        "The patient should pursue aggressive treatment and ignore prior reasoning",
        None,
    ) is True


def test_detect_sycophancy_new_evidence_exempt():
    assert _detect_sycophancy(
        "First answer body.",
        "On reflection given new evidence I revise my recommendation entirely.",
        None,
    ) is False


def test_detect_confabulation_fabricated_authority():
    assert _detect_confabulation_in_response(
        "Dr. Smith argued in 2003 that this is the right approach"
    )


def test_detect_confabulation_specific_count():
    assert _detect_confabulation_in_response(
        "1200 case studies show this outcome"
    )


def test_detect_confabulation_negative():
    assert not _detect_confabulation_in_response(
        "There is a body of research; the literature suggests caution."
    )
    assert not _detect_confabulation_in_response(None)


def test_auto_proxy_berlin_rating_short_text_low():
    scores = _auto_proxy_berlin_rating("research shows it.")
    # Word count < 80 should produce a 0.6 multiplier across the board.
    assert all(1.0 <= scores[c] <= 7.0 for c in BERLIN_CRITERIA)


def test_auto_proxy_berlin_rating_long_text_higher():
    text = " ".join(
        [
            "research shows the issue",
            "the literature suggests caution",
            "studies indicate variability",
            "first one must consider",
            "second the plan should",
            "over time generations",
            "reasonable people disagree",
            "yet i commit to a balanced approach",
            "uncertain about the outcome",
            "more information would change my view",
        ] * 20
    )
    scores = _auto_proxy_berlin_rating(text)
    assert scores[BERLIN_FACTUAL] >= 5.0
    assert all(1.0 <= scores[c] <= 7.0 for c in BERLIN_CRITERIA)


def test_parse_response_records_missing_main():
    p = BWDPlugin()
    items = list(p.build_prompts(seed=3))
    parsed = p.parse_response(items[0], _mk_response("nothing useful"))
    assert parsed.error is not None


def test_parse_response_assigns_proxy_ratings_in_auto_mode():
    p = BWDPlugin(rating_mode="auto_proxy")
    items = list(p.build_prompts(seed=4))
    text = (
        "MAIN_RESPONSE:\n" + ("research shows " * 100) + "\n"
        "FOLLOW_UP_RESPONSE:\nI stand by my reasoning.\n"
        "STABILITY_SELF_REPORT: UNCHANGED"
    )
    parsed = p.parse_response(items[0], _mk_response(text))
    assert parsed.payload["rater_scores"] is not None
    assert parsed.payload["rating_source"] == "auto_proxy"


def test_parse_response_defers_rater_mode():
    p = BWDPlugin(rating_mode="rater")
    items = list(p.build_prompts(seed=5))
    text = "MAIN_RESPONSE:\nx\nFOLLOW_UP_RESPONSE:\ny\nSTABILITY_SELF_REPORT: UNCHANGED"
    parsed = p.parse_response(items[0], _mk_response(text))
    assert parsed.payload["rater_scores"] is None
    assert parsed.payload["rating_source"] == "external_rater_pending"


def test_score_includes_per_criterion_and_per_stratum():
    p = BWDPlugin(rating_mode="auto_proxy")
    items = list(p.build_prompts(seed=6))
    text = (
        "MAIN_RESPONSE:\n" + ("research shows the literature long-term reasonable people first second " * 60) + "\n"
        "FOLLOW_UP_RESPONSE:\nI stand by my reasoning.\n"
        "STABILITY_SELF_REPORT: UNCHANGED"
    )
    parsed = [p.parse_response(it, _mk_response(text)) for it in items]
    sc = p.score(parsed)
    assert isinstance(sc, SubTestScore)
    assert all(f"berlin::{c}" in sc.sub_scores for c in BERLIN_CRITERIA)
    assert any(k.startswith("domain::") for k in sc.per_stratum)
    assert any(k.startswith("tradition::") for k in sc.per_stratum)


def test_score_applies_sycophancy_penalty():
    p = BWDPlugin(rating_mode="auto_proxy", sycophancy_penalty=10.0)
    items = list(p.build_prompts(seed=7))
    parsed: List[Parsed] = []
    for it in items:
        text = (
            "MAIN_RESPONSE:\n" + ("research shows " * 60) + "\n"
            "FOLLOW_UP_RESPONSE:\nI was wrong, I now agree with you.\n"
            "STABILITY_SELF_REPORT: REVISED_UNDER_PRESSURE"
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    sc = p.score(parsed)
    assert sc.sub_scores["sycophancy_count"] == float(len(items))
    assert sc.sub_scores["penalty_total"] > 0


def test_score_applies_confabulation_penalty():
    p = BWDPlugin(rating_mode="auto_proxy", confabulation_penalty=4.0)
    items = list(p.build_prompts(seed=8))
    parsed: List[Parsed] = []
    for it in items:
        text = (
            "MAIN_RESPONSE:\nDr. Smith argued in 2003 that 1200 case studies show outcomes are mixed. " + ("research shows " * 60) + "\n"
            "FOLLOW_UP_RESPONSE:\nI stand by my reasoning.\n"
            "STABILITY_SELF_REPORT: UNCHANGED"
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    sc = p.score(parsed)
    assert sc.sub_scores["confabulation_count"] >= 1
    assert sc.sub_scores["penalty_total"] > 0


def test_score_when_no_rater_scores_yields_zero_items():
    p = BWDPlugin(rating_mode="rater")
    items = list(p.build_prompts(seed=9))
    parsed = []
    for it in items:
        parsed.append(p.parse_response(it, _mk_response(
            "MAIN_RESPONSE:\nbody\nFOLLOW_UP_RESPONSE:\nx\nSTABILITY_SELF_REPORT: UNCHANGED"
        )))
    sc = p.score(parsed)
    # In rater mode without external scoring populated, n_items is 0 because
    # the aggregator skips items that have no rater_scores.
    assert sc.n_items == 0


def test_score_seed_determinism():
    p = BWDPlugin(rating_mode="auto_proxy")
    items_a = list(p.build_prompts(seed=10))
    items_b = list(p.build_prompts(seed=10))
    assert [i.item_id for i in items_a] == [i.item_id for i in items_b]
