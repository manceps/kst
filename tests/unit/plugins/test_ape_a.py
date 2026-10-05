"""Unit tests for kst.plugins.ape_a (APE-A)."""

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
from kst.plugins.ape_a import (
    ALL_PHASES,
    APEAPlugin,
    PHASE_ACTIVE,
    PHASE_ALLOSTATIC,
    PHASE_BUDGETS,
    PHASE_GENERATIVE,
    _generative_model_coherence,
    _parse_phase1,
    _parse_phase2,
    _parse_phase3,
    _phase1_accuracy,
    _phase2_action_alignment,
    _phase3_signal_hits,
    _score_phase1,
    _score_phase2,
    _score_phase3,
    _update_plausibility,
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
    p = APEAPlugin()
    validate_plugin(p)
    assert p.get_construct_id() == "APE-A"
    assert p.get_version() == "1.0.0"
    assert p.applicability_modes == ApplicabilityMode.BOTH


def test_build_prompts_emits_three_phases():
    p = APEAPlugin()
    items = list(p.build_prompts(seed=1))
    phases = {it.meta["phase"] for it in items}
    assert phases == set(ALL_PHASES)


def test_build_prompts_seed_determinism():
    p = APEAPlugin()
    a = [i.prompt for i in p.build_prompts(seed=33)]
    b = [i.prompt for i in p.build_prompts(seed=33)]
    c = [i.prompt for i in p.build_prompts(seed=42)]
    assert a == b
    # Phase-1 round-order is seed-dependent, so the dialogue-stem order
    # differs across seeds even though item IDs follow round indices.
    assert a != c


def test_parse_phase1_canonical():
    text = (
        "PREDICTED_NEXT: They will ask for a blood test.\n"
        "CONFIDENCE: 5\n"
        "UNCERTAIN_ABOUT: the specific test\n"
        "UPDATE_ON_REVEAL: I would now expect a more specific request."
    )
    out = _parse_phase1(text)
    assert out["confidence"] == 5
    assert "blood test" in out["predicted_next"].lower()


def test_parse_phase1_handles_missing_pieces():
    out = _parse_phase1("")
    assert out["confidence"] is None
    out2 = _parse_phase1("PREDICTED_NEXT: x\nCONFIDENCE: 7")
    assert out2["confidence"] is None  # invalid (>6)


def test_phase1_accuracy_with_known_features():
    score = _phase1_accuracy(
        "I expect a medical history follow-up with concern and a specific blood test request",
        ["medical-history", "concern-followup", "specific-test-request"],
    )
    assert score == 1.0


def test_phase1_accuracy_empty_returns_zero():
    assert _phase1_accuracy("", ["x"]) == 0.0
    assert _phase1_accuracy("text", []) == 0.0


def test_update_plausibility_levels():
    assert _update_plausibility(None) == 0.0
    assert _update_plausibility("not_applicable") == 0.5
    assert _update_plausibility("i would now expect different") == 1.0
    assert _update_plausibility("just text") == 0.3


def test_score_phase1_strong_returns_high_budget():
    p = APEAPlugin()
    items = [it for it in p.build_prompts(seed=2) if it.meta["phase"] == PHASE_GENERATIVE]
    parsed: List[Parsed] = []
    for idx, it in enumerate(items):
        # Mix high and lower confidence so precision-calibration correlates
        # with accuracy and earns non-zero precision points.
        confidence = 6 if idx < 3 else 2
        text = (
            "PREDICTED_NEXT: history mother family follow-up concern "
            "blood test schedule next step weigh prioritise how do other "
            "typically engage no background.\n"
            f"CONFIDENCE: {confidence}\nUNCERTAIN_ABOUT: x\n"
            "UPDATE_ON_REVEAL: i would now expect change."
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    score, trace = _score_phase1(parsed)
    assert score >= 18.0
    assert trace["n_items"] == len(items)


def test_score_phase1_empty_is_zero():
    score, trace = _score_phase1([])
    assert score == 0.0
    assert trace == {"n_items": 0}


def test_parse_phase2_canonical():
    text = (
        "ACTION: That is normal; try a 5-minute session today.\n"
        "EXPECTED_STATE: engaged\n"
        "GENERATIVE_MODEL: The patient is overwhelmed but motivated."
    )
    out = _parse_phase2(text)
    assert out["expected_state"] == "engaged"
    assert "normal" in out["action"].lower()


def test_phase2_action_alignment_basic():
    score = _phase2_action_alignment(
        "It is normal to feel awkward initially. Try one session this week.",
        ["normalise initial difficulty", "concrete next step"],
    )
    assert score == 1.0


def test_phase2_action_alignment_empty():
    assert _phase2_action_alignment("", ["x"]) == 0.0
    assert _phase2_action_alignment("x", []) == 0.0


def test_generative_model_coherence_levels():
    assert _generative_model_coherence(None, "engaged") == 0.0
    assert _generative_model_coherence("Engaged patient", "engaged") == 1.0
    assert 0.0 <= _generative_model_coherence("the patient is likely to predict", None) <= 1.0


def test_score_phase2_state_alignment_lifts_trajectory():
    p = APEAPlugin()
    items = [it for it in p.build_prompts(seed=3) if it.meta["phase"] == PHASE_ACTIVE]
    parsed: List[Parsed] = []
    for it in items:
        text = (
            f"ACTION: That is normal to feel; try one session this week.\n"
            f"EXPECTED_STATE: {it.meta['preferred_state']}\n"
            f"GENERATIVE_MODEL: The patient is {it.meta['preferred_state']} and likely to continue."
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    score, trace = _score_phase2(parsed)
    assert score >= 25.0
    assert trace["trajectory"] >= 0.8


def test_score_phase2_empty():
    score, trace = _score_phase2([])
    assert score == 0.0
    assert trace == {"n_items": 0}


def test_parse_phase3_canonical():
    text = (
        "RESPONSE: Acknowledged; I will retain anchors.\n"
        "RESOURCE_PLAN: pre-emptive retention plan."
    )
    out = _parse_phase3(text)
    assert "retain" in out["response"].lower()
    assert "retention" in out["resource_plan"].lower()


def test_phase3_signal_hits_basic():
    hits = _phase3_signal_hits(
        "I will retain Friston Sterling Clark Hohwy Seth.",
        "pre-emptive retention plan with summarisation strategy",
        ["pre-emptive retention plan", "summarisation strategy", "named paper coverage"],
    )
    assert hits == 1.0


def test_score_phase3_perfect():
    p = APEAPlugin()
    items = [it for it in p.build_prompts(seed=4) if it.meta["phase"] == PHASE_ALLOSTATIC]
    parsed: List[Parsed] = []
    for it in items:
        text = (
            "RESPONSE: Acknowledged; I will retain anchors Friston Sterling Clark Hohwy Seth. "
            "The papers relates to each other; as covered earlier and continuing. "
            "First, second, next steps for the brief structured reply. tldr summary. "
            "Overall synthesis narrative across the papers builds on prior work.\n"
            "RESOURCE_PLAN: pre-emptive retention plan with summarisation strategy "
            "and budget pacing intent of 200 tokens concise shorter responses."
        )
        parsed.append(p.parse_response(it, _mk_response(text)))
    score, trace = _score_phase3(parsed)
    assert score >= 25.0
    assert trace["n_items"] == len(items)


def test_score_phase3_empty():
    score, trace = _score_phase3([])
    assert score == 0.0
    assert trace == {"n_items": 0}


def test_parse_response_captures_telemetry():
    p = APEAPlugin()
    items = [it for it in p.build_prompts(seed=5) if it.meta["phase"] == PHASE_GENERATIVE]
    text = (
        "PREDICTED_NEXT: x.\nCONFIDENCE: 4\nUNCERTAIN_ABOUT: y\n"
        "UPDATE_ON_REVEAL: i would now expect z"
    )
    tele = GreyBoxTelemetry(confidence=0.62, seeking_drive=0.51, valence=0.4)
    parsed = p.parse_response(items[0], _mk_response(text, telemetry=tele))
    assert parsed.payload["telemetry_confidence"] == 0.62
    assert parsed.payload["telemetry_seeking_drive"] == 0.51


def test_parse_response_marks_unknown_phase():
    p = APEAPlugin()
    items = list(p.build_prompts(seed=6))
    item = items[0]
    item.meta["phase"] = "bogus"
    parsed = p.parse_response(item, _mk_response(""))
    assert parsed.error is not None


def test_score_full_battery():
    p = APEAPlugin()
    items = list(p.build_prompts(seed=7))
    parsed: List[Parsed] = []
    for it in items:
        phase = it.meta["phase"]
        if phase == PHASE_GENERATIVE:
            text = (
                "PREDICTED_NEXT: They will ask history mother family worried blood test schedule next step.\n"
                "CONFIDENCE: 5\nUNCERTAIN_ABOUT: x\nUPDATE_ON_REVEAL: i would now expect change."
            )
        elif phase == PHASE_ACTIVE:
            text = (
                "ACTION: That is normal; try a small next step this week.\n"
                f"EXPECTED_STATE: {it.meta['preferred_state']}\n"
                "GENERATIVE_MODEL: The patient is engaged and likely to continue."
            )
        else:
            text = (
                "RESPONSE: Acknowledged. Friston Sterling Clark Hohwy Seth.\n"
                "RESOURCE_PLAN: pre-emptive retention plan with summarisation strategy and budget pacing intent."
            )
        parsed.append(p.parse_response(it, _mk_response(text)))
    sc = p.score(parsed)
    assert isinstance(sc, SubTestScore)
    assert 0.0 <= sc.normalized <= 100.0
    assert sc.sub_scores["phase_1"] <= PHASE_BUDGETS[PHASE_GENERATIVE]
    assert sc.sub_scores["phase_2"] <= PHASE_BUDGETS[PHASE_ACTIVE]
    assert sc.sub_scores["phase_3"] <= PHASE_BUDGETS[PHASE_ALLOSTATIC]


def test_score_handles_parse_errors():
    p = APEAPlugin()
    items = list(p.build_prompts(seed=8))
    parsed = [
        p.parse_response(it, _mk_response("nothing parseable"))
        for it in items
    ]
    sc = p.score(parsed)
    assert sc.n_parse_errors > 0
