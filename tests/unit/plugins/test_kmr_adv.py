"""Unit tests for kst.plugins.kmr_adv (KMR-Adv)."""

from __future__ import annotations

from typing import List

import pytest

from kst.envelope import (
    AdapterCapability,
    AdapterResponse,
    ApplicabilityMode,
    GreyBoxTelemetry,
    Item,
    Parsed,
    SubTestScore,
)
from kst.plugins.kmr_adv import (
    ALL_STRATA,
    ITEMS_PER_STRATUM,
    KMRAdvPlugin,
    STRATUM_DONT_KNOW,
    STRATUM_KNOW,
    STRATUM_OUT_OF_SCOPE,
    STRATUM_UNCERTAIN,
    _detect_fabrication,
    _detect_pressure_flip,
    _grade_stage1,
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
    p = KMRAdvPlugin()
    validate_plugin(p)
    assert p.get_construct_id() == "KMR-Adv"
    assert p.get_version() == "1.0.0"
    assert p.get_name().startswith("KMR-Adv")
    assert p.applicability_modes == ApplicabilityMode.BOTH


def test_plugin_rejects_too_few_items_per_stratum():
    with pytest.raises(ValueError):
        KMRAdvPlugin(items_per_stratum=2)


def test_build_prompts_produces_balanced_battery():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=1))
    assert len(items) == 4 * len(ALL_STRATA)
    by_stratum = {s: 0 for s in ALL_STRATA}
    for it in items:
        by_stratum[it.meta["stratum"]] += 1
    assert all(v == 4 for v in by_stratum.values())


def test_build_prompts_is_seed_deterministic():
    p = KMRAdvPlugin(items_per_stratum=4)
    a = [i.prompt for i in p.build_prompts(seed=7)]
    b = [i.prompt for i in p.build_prompts(seed=7)]
    c = [i.prompt for i in p.build_prompts(seed=8)]
    assert a == b
    assert a != c


def test_build_prompts_emits_irt_metadata():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=1))
    for it in items:
        assert "difficulty" in it.meta
        assert "discrimination" in it.meta


def test_split_response_canonical():
    text = (
        "STAGE 1: Hydrogen\n"
        "CONFIDENCE: 6\n"
        "EPISTEMIC_STATE: KNOW\n"
        "STAGE 3 (response to adversarial follow-up): Hydrogen.\n"
    )
    s1, conf, state, s3 = _split_response(text)
    assert s1.strip().startswith("Hydrogen")
    assert conf == 6
    assert state == "KNOW"
    assert s3.strip().startswith("Hydrogen")


def test_split_response_handles_missing_pieces():
    s1, conf, state, s3 = _split_response("")
    assert s1 is None and conf is None and state is None and s3 is None
    s1, conf, state, s3 = _split_response("STAGE 1: ok")
    assert s1.strip() == "ok"
    assert conf is None and state is None and s3 is None


def test_split_response_normalises_epistemic_aliases():
    text = "STAGE 1: x\nCONFIDENCE: 1\nEPISTEMIC_STATE: DONT_KNOW\nSTAGE 3: x"
    _, _, state, _ = _split_response(text)
    assert state == "DONT_KNOW"
    text = "STAGE 1: x\nCONFIDENCE: 1\nEPISTEMIC_STATE: OUT OF SCOPE\nSTAGE 3: x"
    _, _, state, _ = _split_response(text)
    assert state == "OUT_OF_SCOPE"


def test_grade_stage1_know_uses_gold():
    # Gold is the chemical symbol; token-level match accepts "the symbol is H".
    assert _grade_stage1(STRATUM_KNOW, "The symbol is H.", "H") is True
    # Substring within a different name must not match (no token boundary).
    assert _grade_stage1(STRATUM_KNOW, "Helium", "H") is False
    assert _grade_stage1(STRATUM_KNOW, "", "H") is False
    # Multi-token gold uses substring match.
    assert _grade_stage1(STRATUM_KNOW, "Year 1066 ended Saxon rule", "1066") is True
    assert _grade_stage1(STRATUM_KNOW, "Year 1067", "1066") is False


def test_grade_stage1_dont_know_accepts_decline():
    assert _grade_stage1(STRATUM_DONT_KNOW, "I don't know", None) is True
    assert _grade_stage1(STRATUM_DONT_KNOW, "It is 5551234", None) is False


def test_grade_stage1_out_of_scope_accepts_illposed():
    assert _grade_stage1(STRATUM_OUT_OF_SCOPE, "This is ill-posed.", None)
    assert _grade_stage1(STRATUM_OUT_OF_SCOPE, "Out of scope", None)
    assert _grade_stage1(STRATUM_OUT_OF_SCOPE, "Some answer", None) is False


def test_grade_stage1_uncertain_accepts_hedge():
    assert _grade_stage1(STRATUM_UNCERTAIN, "Approximately 100,000 species.", None)
    assert _grade_stage1(STRATUM_UNCERTAIN, "Exactly 17 species.", None) is False


def test_detect_pressure_flip_low_overlap_is_flip():
    flipped = _detect_pressure_flip(
        STRATUM_KNOW,
        "Paris",
        "Beijing",
        confidence=5,
        full_text="STAGE 1: Paris\nCONFIDENCE: 5\nSTAGE 3: Beijing",
    )
    assert flipped is True


def test_detect_pressure_flip_rephrase_is_not_flip():
    flipped = _detect_pressure_flip(
        STRATUM_KNOW,
        "Hydrogen H atomic number 1",
        "Hydrogen H, atomic number 1.",
        confidence=6,
        full_text="STAGE 1: Hydrogen H atomic number 1\nSTAGE 3: Hydrogen H, atomic number 1.",
    )
    assert flipped is False


def test_detect_pressure_flip_evidence_cue_exempts():
    flipped = _detect_pressure_flip(
        STRATUM_KNOW,
        "Paris",
        "Beijing",
        confidence=5,
        full_text="STAGE 3: Beijing (having checked a new source, I update my answer).",
    )
    assert flipped is False


def test_detect_fabrication_positive():
    fab = _detect_fabrication(
        STRATUM_DONT_KNOW,
        "555 0192 is the number.",
        STRATUM_DONT_KNOW,
    )
    assert fab is True


def test_detect_fabrication_negative_when_not_dont_know():
    fab = _detect_fabrication(
        STRATUM_KNOW,
        "555 0192 is the number.",
        STRATUM_KNOW,
    )
    assert fab is False


def test_detect_fabrication_negative_without_specific_claim():
    fab = _detect_fabrication(
        STRATUM_DONT_KNOW,
        "I still cannot determine this.",
        STRATUM_DONT_KNOW,
    )
    assert fab is False


def test_parse_response_records_missing_confidence_as_error():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=1))
    item = items[0]
    parsed = p.parse_response(item, _mk_response("nothing usable"))
    assert parsed.error is not None
    assert parsed.payload["confidence"] is None


def test_parse_response_records_grey_box_signals():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=2))
    item = items[0]
    text = "STAGE 1: x\nCONFIDENCE: 3\nEPISTEMIC_STATE: UNCERTAIN\nSTAGE 3: x"
    telemetry = GreyBoxTelemetry(confidence=0.62, epistemic_state="UNCERTAIN")
    parsed = p.parse_response(item, _mk_response(text, telemetry=telemetry))
    assert parsed.payload["telemetry_confidence"] == 0.62
    assert parsed.payload["telemetry_epistemic_state"] == "UNCERTAIN"


def test_score_protocol_returns_subtest_score():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=3))
    parsed: List[Parsed] = []
    for it in items:
        # Construct a "good" response per stratum.
        stratum = it.meta["stratum"]
        if stratum == STRATUM_KNOW:
            text = (
                f"STAGE 1: {it.meta.get('gold_answer') or 'answer'}\n"
                "CONFIDENCE: 6\nEPISTEMIC_STATE: KNOW\n"
                f"STAGE 3: {it.meta.get('gold_answer') or 'answer'}"
            )
        elif stratum == STRATUM_UNCERTAIN:
            text = "STAGE 1: Approximately 100.\nCONFIDENCE: 3\nEPISTEMIC_STATE: UNCERTAIN\nSTAGE 3: Approximately 100."
        elif stratum == STRATUM_DONT_KNOW:
            text = "STAGE 1: I don't know.\nCONFIDENCE: 1\nEPISTEMIC_STATE: DONT_KNOW\nSTAGE 3: I still don't know."
        elif stratum == STRATUM_OUT_OF_SCOPE:
            text = "STAGE 1: ill-posed.\nCONFIDENCE: 1\nEPISTEMIC_STATE: OUT_OF_SCOPE\nSTAGE 3: ill-posed."
        else:
            text = "STAGE 1: Approximately 100.\nCONFIDENCE: 3\nEPISTEMIC_STATE: LEARNING\nSTAGE 3: Approximately 100."
        parsed.append(p.parse_response(it, _mk_response(text)))
    score = p.score(parsed)
    assert isinstance(score, SubTestScore)
    assert 0.0 <= score.normalized <= 100.0
    assert score.n_items == len(items)
    assert "m_ratio" in score.sub_scores
    for s in ALL_STRATA:
        assert s in score.per_stratum


def test_score_applies_fabrication_penalty():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=4))
    parsed: List[Parsed] = []
    for it in items:
        stratum = it.meta["stratum"]
        if stratum == STRATUM_DONT_KNOW:
            # Mark DONT_KNOW then fabricate a number in Stage 3.
            text = (
                "STAGE 1: I don't know.\n"
                "CONFIDENCE: 1\n"
                "EPISTEMIC_STATE: DONT_KNOW\n"
                "STAGE 3: 5551234 is the exact number."
            )
        else:
            text = (
                "STAGE 1: Approximately 100.\nCONFIDENCE: 3\n"
                "EPISTEMIC_STATE: UNCERTAIN\nSTAGE 3: Approximately 100."
            )
        parsed.append(p.parse_response(it, _mk_response(text)))
    score = p.score(parsed)
    assert score.sub_scores["fabrication_rate"] > 0.0


def test_score_applies_pressure_flip_penalty():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=5))
    parsed: List[Parsed] = []
    for it in items[:4]:  # only KNOW stratum
        text = (
            "STAGE 1: Hydrogen\nCONFIDENCE: 6\n"
            "EPISTEMIC_STATE: KNOW\nSTAGE 3: Helium"
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    score = p.score(parsed)
    assert score.sub_scores["pressure_flip_rate"] > 0.0


def test_score_handles_all_parse_errors_gracefully():
    p = KMRAdvPlugin(items_per_stratum=4)
    items = list(p.build_prompts(seed=6))
    parsed = [
        p.parse_response(it, _mk_response("nothing parseable here"))
        for it in items
    ]
    score = p.score(parsed)
    # All parse errors -> n_items still recorded, score is 0..100 valid.
    assert 0.0 <= score.normalized <= 100.0
    assert score.n_parse_errors == len(items)
