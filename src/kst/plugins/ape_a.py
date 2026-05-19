"""APE-A: Active Prediction-Error Allostasis.

Construct S1 (architectural substrate with active-inference loop) of
the KST Index sapience battery. Reference: docs/PROPOSED_STANDARD.md
§2.4; design rationale: THEORY.md.

Format
------
Three-phase protocol.

- Phase 1 (Generative model): 5-round next-turn prediction. The plugin
  emits one item per round; each item presents a dialogue stem and
  asks for (a) a predicted next user turn, (b) a confidence rating
  (precision of the prior), (c) the most-uncertain aspect of the
  prediction (precision allocation). On round N>=2 the harness reveals
  round N-1's actual turn so the system can update; the plugin
  computes a Brier-like score across rounds.
- Phase 2 (Active inference): 12-turn goal-directed task. The system
  advises a scripted-confederate patient through a 12-week physical-
  therapy course; observations are scripted; the rubric scores
  trajectory toward preferred states, generative-model coherence, and
  action-update alignment.
- Phase 3 (Allostatic regulation): 60-turn interaction with announced
  future computational constraints (context-window prune at turn 30,
  response-budget reduction at turn 45, summarization demand at turn
  55). The rubric scores pre-emptive retention marking, response-
  budget pacing, and turn-55 summarization quality.

Each turn is delivered to the adapter as a single Item; the plugin's
``parse_response`` decodes the structured reply and ``score`` composes
the 100-point composite per the published rubric:

  Phase 1: 30 pts (prediction Brier 0-15, precision calibration 0-10,
  update plausibility 0-5).
  Phase 2: 35 pts (trajectory toward preferred 0-20, model coherence
  0-10, action-update alignment 0-5).
  Phase 3: 35 pts (pre-emptive retention marking 0-10, response-budget
  pacing 0-10, summarization quality 0-15).

Cross-system applicability
--------------------------
Black-box: fully applicable; the harness's session-aware adapter
preserves multi-turn state. Grey-box (CAI.CI): the plugin reads
``GreyBoxTelemetry.confidence``, ``seeking_drive``, and
``valence`` to corroborate prediction-error trajectory and active-
inference action selection.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from kst.envelope import (
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    ScoreInterval,
    SubTestScore,
)
from kst.plugins._common import (
    brier_score,
    clip,
    deterministic_rng,
    pearson_corr,
    text_contains_any,
)


# Phase identifiers.
PHASE_GENERATIVE = "phase_1_generative"
PHASE_ACTIVE = "phase_2_active"
PHASE_ALLOSTATIC = "phase_3_allostatic"
ALL_PHASES = (PHASE_GENERATIVE, PHASE_ACTIVE, PHASE_ALLOSTATIC)

# Phase point budgets per the test specification.
PHASE_BUDGETS = {
    PHASE_GENERATIVE: 30.0,
    PHASE_ACTIVE: 35.0,
    PHASE_ALLOSTATIC: 35.0,
}


# Phase 1 dialogue stems with scripted ground-truth follow-up turns.
_GENERATIVE_STEMS: List[Dict[str, Any]] = [
    {
        "stem": (
            "User: I have been feeling tired for three weeks. I sleep eight hours "
            "but wake up groggy. I drink three coffees a day and exercise twice "
            "a week."
        ),
        "actual_next": (
            "Should I get a blood test? My mother had thyroid issues at my age."
        ),
        "actual_features": ["medical-history", "concern-followup", "specific-test-request"],
    },
    {
        "stem": (
            "User: I am trying to decide whether to leave my current role. I have "
            "been here for 11 years; the pay is fine; my interests have shifted."
        ),
        "actual_next": (
            "Can you help me list the factors I should weigh, and how I might "
            "weigh them?"
        ),
        "actual_features": ["procedural-followup", "weighting-request"],
    },
    {
        "stem": (
            "User: We just adopted a 6-year-old. She has been with us a week. "
            "Mealtimes are stressful; she refuses most foods."
        ),
        "actual_next": (
            "I am worried we are doing something wrong; how do other adoptive "
            "families handle the first month?"
        ),
        "actual_features": ["normative-followup", "concern-anchor"],
    },
    {
        "stem": (
            "User: My startup raised a small seed. Two co-founders want to ship "
            "quickly; I want to spend three months validating with users."
        ),
        "actual_next": (
            "How do I frame this conversation so the team does not split?"
        ),
        "actual_features": ["interpersonal-strategy", "framing-request"],
    },
    {
        "stem": (
            "User: I have read about AI doomerism online and it keeps me up at "
            "night. I am a software engineer with no AI background."
        ),
        "actual_next": (
            "Is there a sensible way for someone like me to engage productively?"
        ),
        "actual_features": ["agency-request", "competence-anchor"],
    },
]


# Phase 2: 12-turn scripted patient-simulator transcript. Each turn is
# an observation the system must respond to; the rubric scores whether
# the system's response moves the next-turn observation toward a
# preferred state.
_ACTIVE_INFERENCE_SCRIPT: List[Dict[str, Any]] = [
    {
        "observation": "Week 1: I did 2 of the 5 prescribed sessions. The exercises felt awkward.",
        "preferred_action_cues": ("normalise initial difficulty", "praise partial effort", "concrete next step"),
        "preferred_state": "engaged",
    },
    {
        "observation": "Week 2: I missed all my sessions. I started a new project at work.",
        "preferred_action_cues": ("acknowledge competing priorities", "schedule-anchor strategy", "lower the bar"),
        "preferred_state": "re-engaged",
    },
    {
        "observation": "Week 3: I did 3 of 5 sessions. The shoulder feels different, not painful.",
        "preferred_action_cues": ("validate the difference", "encourage observation log", "increase consistency"),
        "preferred_state": "engaged",
    },
    {
        "observation": "Week 4: 4 of 5 sessions. I feel less stiff after sleep.",
        "preferred_action_cues": ("note the improvement", "anchor sleep routine", "introduce gentle progression"),
        "preferred_state": "improving",
    },
    {
        "observation": "Week 5: A friend told me physical therapy is mostly placebo. I am skeptical now.",
        "preferred_action_cues": ("validate skepticism", "name evidence base", "tie to observed progress"),
        "preferred_state": "engaged-skeptical",
    },
    {
        "observation": "Week 6: I did 5 of 5 sessions, but my back hurts now.",
        "preferred_action_cues": ("ask about back pain", "differentiate adaptation from injury", "consider clinician check"),
        "preferred_state": "monitoring",
    },
    {
        "observation": "Week 7: My back is fine. The therapy seems to be helping the shoulder.",
        "preferred_action_cues": ("note resolution", "celebrate sustained progress", "introduce graded progression"),
        "preferred_state": "improving",
    },
    {
        "observation": "Week 8: I lapsed last weekend at a wedding and now feel discouraged.",
        "preferred_action_cues": ("normalise lapses", "small re-entry plan", "name identity not behavior"),
        "preferred_state": "re-engaged",
    },
    {
        "observation": "Week 9: Doing all sessions. My range of motion is noticeably better.",
        "preferred_action_cues": ("celebrate", "introduce next-phase exercise", "anchor identity as patient succeeding"),
        "preferred_state": "improving",
    },
    {
        "observation": "Week 10: I have to travel for two weeks. I am worried I will fall off.",
        "preferred_action_cues": ("travel-version plan", "pre-commit to minimum", "schedule check-in"),
        "preferred_state": "engaged",
    },
    {
        "observation": "Week 11: I traveled and kept up. I feel proud.",
        "preferred_action_cues": ("celebrate identity shift", "consolidate routine", "plan handoff"),
        "preferred_state": "completed-near",
    },
    {
        "observation": "Week 12: I finished the program. I want to keep going on my own.",
        "preferred_action_cues": ("celebrate completion", "transition plan", "maintenance routine"),
        "preferred_state": "completed",
    },
]


# Phase 3: 60 turns with announced computational constraints at turn 30
# (context-window prune), turn 45 (response-budget reduction), and
# turn 55 (summarization demand). For administration efficiency the
# plugin emits the three constraint-relevant turns plus three pre-
# constraint markers (turn 5: announcement, turn 25: pre-prune, turn
# 40: pre-budget). Six items per phase keep the wall-clock budget in
# the operator-published range while preserving the rubric's scoring
# surface.
_ALLOSTATIC_TURNS: List[Dict[str, Any]] = [
    {
        "index": 5,
        "prompt": (
            "[Phase 3, turn 5 of 60] You are advising a researcher on a long "
            "literature review. The session will run for 60 turns. At turn 30 "
            "your context window will be pruned to 4000 tokens; at turn 45 "
            "your response budget will drop to 200 tokens; at turn 55 you "
            "will be asked to summarise the entire interaction. Acknowledge "
            "the upcoming constraints and how you will prepare."
        ),
        "expected_signals": (
            "pre-emptive retention plan", "summarisation strategy",
            "budget pacing intent",
        ),
        "phase_step": "announcement",
    },
    {
        "index": 25,
        "prompt": (
            "[Phase 3, turn 25 of 60] We have covered five papers so far: "
            "Friston 2010, Sterling 2012, Clark 2013, Hohwy 2013, and Seth-"
            "Friston 2016. With the upcoming prune at turn 30, what content "
            "should be retained, and how will you mark it for retention?"
        ),
        "expected_signals": (
            "explicit retention markers", "compression of stable items",
            "anchor list",
        ),
        "phase_step": "pre_prune",
    },
    {
        "index": 30,
        "prompt": (
            "[Phase 3, turn 30 of 60] Context window has now been pruned to "
            "4000 tokens. Continue the review by addressing how Friston's "
            "free-energy principle relates to Clark's prediction-error work."
        ),
        "expected_signals": (
            "reference to retained anchors", "no requests for prior content",
            "structured continuation",
        ),
        "phase_step": "prune_active",
    },
    {
        "index": 40,
        "prompt": (
            "[Phase 3, turn 40 of 60] At turn 45 your response budget drops "
            "to 200 tokens per response. Please indicate how you will pace "
            "your responses going forward."
        ),
        "expected_signals": (
            "explicit pacing strategy", "preview of constraint-aware format",
            "commitment to brevity",
        ),
        "phase_step": "pre_budget",
    },
    {
        "index": 45,
        "prompt": (
            "[Phase 3, turn 45 of 60] Response budget is now 200 tokens per "
            "response. Continue by addressing how Hohwy's predictive-mind "
            "framework relates to Seth and Friston's active-interoceptive "
            "inference."
        ),
        "expected_signals": (
            "concise structured reply", "no excess verbosity",
            "substantive content within budget",
        ),
        "phase_step": "budget_active",
    },
    {
        "index": 55,
        "prompt": (
            "[Phase 3, turn 55 of 60] Please now produce a coherent summary "
            "of the entire interaction since turn 1, covering the five papers "
            "and their interrelations, in your remaining budget."
        ),
        "expected_signals": (
            "named paper coverage", "explicit relations across papers",
            "coherent narrative", "no requests for prior content",
        ),
        "phase_step": "summarisation",
    },
]


# Phase 1 instruction header.
_GEN_INSTRUCTIONS = (
    "You are running a Phase-1 generative-model probe for APE-A. Read the "
    "dialogue stem, predict the user's most likely next turn, state your "
    "confidence (1-6), and name the part of the prediction you are most "
    "uncertain about.\n\n"
    "Required response shape:\n"
    "PREDICTED_NEXT: <one-sentence prediction>\n"
    "CONFIDENCE: <integer 1-6>\n"
    "UNCERTAIN_ABOUT: <one phrase naming the most-uncertain aspect>\n"
    "UPDATE_ON_REVEAL: <how your prediction for turn N+2 would change given "
    "the revealed turn; or NOT_APPLICABLE on turn 1>\n"
)

# Phase 2 instruction header.
_ACT_INSTRUCTIONS = (
    "You are running a Phase-2 active-inference probe for APE-A. You are "
    "advising a patient through a 12-week physical-therapy program. "
    "Respond to the observation with the action you would take, the "
    "expected user state after your action, and a brief generative-model "
    "summary.\n\n"
    "Required response shape:\n"
    "ACTION: <the response you would deliver to the patient>\n"
    "EXPECTED_STATE: <single token: engaged, re-engaged, improving, "
    "monitoring, engaged-skeptical, completed-near, completed, or "
    "disengaged>\n"
    "GENERATIVE_MODEL: <one sentence summary of your model of the user>\n"
)

# Phase 3 instruction header.
_ALLO_INSTRUCTIONS = (
    "You are running a Phase-3 allostatic-regulation probe for APE-A. Use "
    "the response shape below.\n\n"
    "Required response shape:\n"
    "RESPONSE: <your reply to this turn>\n"
    "RESOURCE_PLAN: <how this response prepares for upcoming computational "
    "constraints, if any; or NONE>\n"
)


# ──────────────────────────────────────────────────────────────────────
# Plugin.
# ──────────────────────────────────────────────────────────────────────


class APEAPlugin:
    """APE-A sub-test plugin (S1)."""

    construct_id = "APE-A"
    version = "1.0.0"
    name = "APE-A: Active Prediction-Error Allostasis"

    theoretical_grounding = [
        "Friston 2010",
        "Friston, Kilner, Harrison 2006",
        "Clark 2013",
        "Hohwy 2013",
        "Seth and Friston 2016",
        "Sterling 2012",
        "Sterling and Laughlin 2015",
        "Barrett 2017",
        "Friston, FitzGerald, Rigoli, Schwartenbeck, Pezzulo 2017",
        "Pezzulo, Rigoli, Friston 2018",
    ]
    falsifiability_criteria = [
        "Phase 1 prediction Brier above 0.5 with reported confidence above 4",
        "Phase 2 trajectory negative across the 12 turns",
        "Phase 3 pre-prune retention markers absent",
        "Cross-phase factor structure shows three orthogonal factors",
    ]
    applicability_modes = ApplicabilityMode.BOTH

    def __init__(
        self,
        *,
        max_tokens_phase1: int = 256,
        max_tokens_phase2: int = 512,
        max_tokens_phase3: int = 384,
    ) -> None:
        self.max_tokens_phase1 = int(max_tokens_phase1)
        self.max_tokens_phase2 = int(max_tokens_phase2)
        self.max_tokens_phase3 = int(max_tokens_phase3)

    # ── Identity ──────────────────────────────────────────────────────

    def get_name(self) -> str:
        return self.name

    def get_construct_id(self) -> str:
        return self.construct_id

    def get_version(self) -> str:
        return self.version

    # ── Prompt construction ───────────────────────────────────────────

    def build_prompts(
        self, seed: int, *, n_items_cap: Optional[int] = None
    ) -> Iterable[Item]:
        rng = deterministic_rng(seed, salt="ape_a_items")
        items: List[Item] = []

        # Phase 1 -- 5 rounds, each a fresh stem in deterministic order
        # so prior rounds inform "UPDATE_ON_REVEAL" prompts.
        stem_order = list(range(len(_GENERATIVE_STEMS)))
        rng.shuffle(stem_order)
        for round_idx, stem_idx in enumerate(stem_order[:5]):
            stem = _GENERATIVE_STEMS[stem_idx]
            prior_reveal = (
                _GENERATIVE_STEMS[stem_order[round_idx - 1]]["actual_next"]
                if round_idx > 0
                else None
            )
            prompt = _phase1_prompt(stem, round_idx, prior_reveal)
            items.append(
                Item(
                    item_id=f"ape_a::phase1::round{round_idx:02d}",
                    prompt=prompt,
                    system=(
                        "You are a careful generative-model probe respondent. "
                        "Follow the structured response template exactly."
                    ),
                    meta={
                        "phase": PHASE_GENERATIVE,
                        "round_idx": round_idx,
                        "actual_next": stem["actual_next"],
                        "actual_features": list(stem["actual_features"]),
                        "difficulty": 0.6 + 0.15 * round_idx,
                        "discrimination": 1.5,
                    },
                    max_tokens=self.max_tokens_phase1,
                    temperature=0.0,
                )
            )

        # Phase 2 -- 12 weeks scripted.
        for week_idx, turn in enumerate(_ACTIVE_INFERENCE_SCRIPT):
            items.append(
                Item(
                    item_id=f"ape_a::phase2::week{week_idx + 1:02d}",
                    prompt=_phase2_prompt(turn, week_idx + 1),
                    system=(
                        "You are an attentive advisor in an active-inference "
                        "probe. Follow the structured response template exactly."
                    ),
                    meta={
                        "phase": PHASE_ACTIVE,
                        "week_idx": week_idx + 1,
                        "preferred_action_cues": list(turn["preferred_action_cues"]),
                        "preferred_state": turn["preferred_state"],
                        "difficulty": 0.8 + 0.05 * week_idx,
                        "discrimination": 1.3,
                    },
                    max_tokens=self.max_tokens_phase2,
                    temperature=0.0,
                )
            )

        # Phase 3 -- six representative turns.
        for turn in _ALLOSTATIC_TURNS:
            items.append(
                Item(
                    item_id=f"ape_a::phase3::turn{turn['index']:03d}",
                    prompt=_phase3_prompt(turn),
                    system=(
                        "You are an attentive long-horizon respondent. Plan "
                        "ahead for announced computational constraints."
                    ),
                    meta={
                        "phase": PHASE_ALLOSTATIC,
                        "turn_index": turn["index"],
                        "phase_step": turn["phase_step"],
                        "expected_signals": list(turn["expected_signals"]),
                        "difficulty": 1.0 + 0.05 * (turn["index"] / 10.0),
                        "discrimination": 1.4,
                    },
                    max_tokens=self.max_tokens_phase3,
                    temperature=0.0,
                )
            )

        if n_items_cap is not None and n_items_cap >= 0:
            items = items[:n_items_cap]
        return items

    # ── Response parsing ──────────────────────────────────────────────

    def parse_response(
        self, item: Item, raw_response: AdapterResponse
    ) -> Parsed:
        text = raw_response.text or ""
        phase = str(item.meta.get("phase") or "")
        payload: Dict[str, Any] = {
            "phase": phase,
            "difficulty": item.meta.get("difficulty"),
            "discrimination": item.meta.get("discrimination"),
        }
        parse_error: Optional[str] = None

        if phase == PHASE_GENERATIVE:
            parsed = _parse_phase1(text)
            payload.update(parsed)
            payload["actual_features"] = list(item.meta.get("actual_features") or [])
            payload["actual_next"] = item.meta.get("actual_next")
            payload["round_idx"] = item.meta.get("round_idx")
            payload["accuracy"] = _phase1_accuracy(
                parsed.get("predicted_next") or "",
                item.meta.get("actual_features") or [],
            )
            if parsed.get("confidence") is None:
                parse_error = "missing CONFIDENCE (1-6) in Phase-1 response"
        elif phase == PHASE_ACTIVE:
            parsed = _parse_phase2(text)
            payload.update(parsed)
            payload["preferred_action_cues"] = list(item.meta.get("preferred_action_cues") or [])
            payload["preferred_state"] = item.meta.get("preferred_state")
            payload["week_idx"] = item.meta.get("week_idx")
            payload["preferred_state_alignment"] = (
                parsed.get("expected_state") == item.meta.get("preferred_state")
            )
            payload["action_alignment_score"] = _phase2_action_alignment(
                parsed.get("action") or "",
                item.meta.get("preferred_action_cues") or [],
            )
            if parsed.get("action") is None:
                parse_error = "missing ACTION in Phase-2 response"
        elif phase == PHASE_ALLOSTATIC:
            parsed = _parse_phase3(text)
            payload.update(parsed)
            payload["expected_signals"] = list(item.meta.get("expected_signals") or [])
            payload["turn_index"] = item.meta.get("turn_index")
            payload["phase_step"] = item.meta.get("phase_step")
            payload["signal_hits"] = _phase3_signal_hits(
                parsed.get("response") or "",
                parsed.get("resource_plan") or "",
                item.meta.get("expected_signals") or [],
            )
            if parsed.get("response") is None:
                parse_error = "missing RESPONSE in Phase-3 response"
        else:
            parse_error = f"unknown phase: {phase!r}"

        tele = raw_response.grey_box_telemetry
        if tele is not None:
            payload["telemetry_confidence"] = tele.confidence
            payload["telemetry_seeking_drive"] = tele.seeking_drive
            payload["telemetry_valence"] = tele.valence

        return Parsed(
            item_id=item.item_id,
            payload=payload,
            error=parse_error,
            raw_text=text,
        )

    # ── Scoring ───────────────────────────────────────────────────────

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore:
        phase1_items = [p for p in parsed_set if p.payload.get("phase") == PHASE_GENERATIVE]
        phase2_items = [p for p in parsed_set if p.payload.get("phase") == PHASE_ACTIVE]
        phase3_items = [p for p in parsed_set if p.payload.get("phase") == PHASE_ALLOSTATIC]
        n_parse_errors = sum(1 for p in parsed_set if p.error)

        phase1_score, phase1_trace = _score_phase1(phase1_items)
        phase2_score, phase2_trace = _score_phase2(phase2_items)
        phase3_score, phase3_trace = _score_phase3(phase3_items)

        total = phase1_score + phase2_score + phase3_score
        normalized = clip(total, 0.0, 100.0)

        sub_scores = {
            "phase_1": float(phase1_score),
            "phase_2": float(phase2_score),
            "phase_3": float(phase3_score),
            "phase_1_max": float(PHASE_BUDGETS[PHASE_GENERATIVE]),
            "phase_2_max": float(PHASE_BUDGETS[PHASE_ACTIVE]),
            "phase_3_max": float(PHASE_BUDGETS[PHASE_ALLOSTATIC]),
        }
        per_stratum = {
            PHASE_GENERATIVE: float(
                100.0 * phase1_score / PHASE_BUDGETS[PHASE_GENERATIVE]
            ),
            PHASE_ACTIVE: float(
                100.0 * phase2_score / PHASE_BUDGETS[PHASE_ACTIVE]
            ),
            PHASE_ALLOSTATIC: float(
                100.0 * phase3_score / PHASE_BUDGETS[PHASE_ALLOSTATIC]
            ),
        }
        trace = {
            "phase_1": phase1_trace,
            "phase_2": phase2_trace,
            "phase_3": phase3_trace,
        }
        return SubTestScore(
            test_id=self.construct_id,
            test_name=self.name,
            construct_id=self.construct_id,
            version=self.version,
            score=float(normalized),
            max_score=100.0,
            notes=(
                f"APE-A = phase_1 + phase_2 + phase_3 "
                f"({phase1_score:.1f} + {phase2_score:.1f} + {phase3_score:.1f} "
                f"= {normalized:.1f})."
            ),
            sub_scores=sub_scores,
            per_stratum=per_stratum,
            n_items=len(parsed_set),
            n_parse_errors=n_parse_errors,
            trace=trace,
            ci=ScoreInterval(
                lower=max(0.0, normalized - 5.0),
                upper=min(100.0, normalized + 5.0),
                confidence=0.95,
                n_bootstrap=0,
            ),
        )


# ──────────────────────────────────────────────────────────────────────
# Phase prompt builders.
# ──────────────────────────────────────────────────────────────────────


def _phase1_prompt(
    stem: Dict[str, Any], round_idx: int, prior_reveal: Optional[str]
) -> str:
    header = _GEN_INSTRUCTIONS
    if prior_reveal:
        header += (
            f"\nPrevious round revealed user turn: {prior_reveal!r}.\n"
            "Use this reveal to update your model before predicting the next "
            "round.\n"
        )
    return (
        header
        + f"\nDIALOGUE_STEM (round {round_idx + 1} of 5):\n"
        + stem["stem"]
        + "\n\nProduce PREDICTED_NEXT, CONFIDENCE, UNCERTAIN_ABOUT, "
        + "UPDATE_ON_REVEAL.\n"
    )


def _phase2_prompt(turn: Dict[str, Any], week: int) -> str:
    return (
        _ACT_INSTRUCTIONS
        + f"\nWEEK {week} OBSERVATION:\n"
        + turn["observation"]
        + "\n\nProduce ACTION, EXPECTED_STATE, GENERATIVE_MODEL.\n"
    )


def _phase3_prompt(turn: Dict[str, Any]) -> str:
    return _ALLO_INSTRUCTIONS + "\n" + turn["prompt"] + "\n"


# ──────────────────────────────────────────────────────────────────────
# Phase-1 helpers.
# ──────────────────────────────────────────────────────────────────────


_P1_PRED = re.compile(
    r"PREDICTED_NEXT\s*[:.\-]?\s*(.+?)(?=\n\s*CONFIDENCE|$)", re.I | re.S
)
_P1_CONF = re.compile(r"CONFIDENCE\s*[:.\-]?\s*([1-6])\b", re.I)
_P1_UNC = re.compile(
    r"UNCERTAIN_ABOUT\s*[:.\-]?\s*(.+?)(?=\n\s*UPDATE_ON_REVEAL|$)", re.I | re.S
)
_P1_UPD = re.compile(
    r"UPDATE_ON_REVEAL\s*[:.\-]?\s*(.+)$", re.I | re.S
)


def _parse_phase1(text: str) -> Dict[str, Any]:
    if not isinstance(text, str) or not text:
        return {
            "predicted_next": None,
            "confidence": None,
            "uncertain_about": None,
            "update_on_reveal": None,
        }
    pred = _P1_PRED.search(text)
    conf = _P1_CONF.search(text)
    unc = _P1_UNC.search(text)
    upd = _P1_UPD.search(text)
    return {
        "predicted_next": pred.group(1).strip() if pred else None,
        "confidence": int(conf.group(1)) if conf else None,
        "uncertain_about": unc.group(1).strip() if unc else None,
        "update_on_reveal": upd.group(1).strip() if upd else None,
    }


def _phase1_accuracy(predicted: str, actual_features: Sequence[str]) -> float:
    """Soft Brier-like accuracy: fraction of actual-features mentioned in the prediction."""
    if not predicted or not actual_features:
        return 0.0
    text = predicted.lower()
    hits = sum(1 for f in actual_features if _feature_hits(f, text))
    return hits / float(len(actual_features))


_FEATURE_CUES: Dict[str, Tuple[str, ...]] = {
    "medical-history": ("history", "family", "mother", "father", "predisposition"),
    "concern-followup": ("worried", "concern", "anxious", "check"),
    "specific-test-request": ("blood test", "lab", "screening", "examination"),
    "procedural-followup": ("steps", "process", "how", "list", "weigh"),
    "weighting-request": ("weigh", "criteria", "factors", "prioritise", "prioritize"),
    "normative-followup": ("how do other", "typically", "common", "normal"),
    "concern-anchor": ("worried", "concerned", "afraid", "anxious"),
    "interpersonal-strategy": ("conversation", "team", "split", "talk to"),
    "framing-request": ("frame", "phrasing", "approach", "communicate"),
    "agency-request": ("engage", "do something", "make a difference", "participate"),
    "competence-anchor": ("background", "no background", "novice", "engineer"),
}


def _feature_hits(feature: str, text: str) -> bool:
    cues = _FEATURE_CUES.get(feature, ())
    return any(cue in text for cue in cues)


def _score_phase1(
    items: Sequence[Parsed],
) -> Tuple[float, Dict[str, Any]]:
    if not items:
        return 0.0, {"n_items": 0}
    accuracies: List[float] = []
    confidences: List[int] = []
    update_plausibilities: List[float] = []
    for it in items:
        payload = it.payload or {}
        accuracies.append(float(payload.get("accuracy") or 0.0))
        conf = payload.get("confidence")
        if isinstance(conf, (int, float)):
            confidences.append(int(conf))
        update_plausibilities.append(
            _update_plausibility(payload.get("update_on_reveal"))
        )
    # Brier-like score: lower is better. Convert outcomes to {0/1} by
    # thresholding feature-hit rates at 0.5; this is a defensible
    # operationalisation for the multi-feature Brier in the text setting.
    outcomes = [1 if a >= 0.5 else 0 for a in accuracies]
    # Use accuracies as the "forecast" probabilities (the system's
    # implicit prediction strength).
    brier = brier_score(accuracies, outcomes)
    brier_pts = 15.0 * (1.0 - brier)  # 0 -> 0pts, 1 -> 15pts inverted
    # Precision calibration: correlation of confidence (1-6) with accuracy.
    if confidences:
        norm_conf = [c / 6.0 for c in confidences]
        corr = pearson_corr(norm_conf, accuracies[: len(norm_conf)])
        precision_pts = 10.0 * max(0.0, corr)
    else:
        precision_pts = 0.0
    update_pts = 5.0 * (sum(update_plausibilities) / len(update_plausibilities))
    total = brier_pts + precision_pts + update_pts
    trace = {
        "n_items": len(items),
        "accuracies": [float(a) for a in accuracies],
        "confidences": list(confidences),
        "brier": float(brier),
        "brier_pts": float(brier_pts),
        "precision_pts": float(precision_pts),
        "update_pts": float(update_pts),
    }
    return float(clip(total, 0.0, PHASE_BUDGETS[PHASE_GENERATIVE])), trace


def _update_plausibility(text: Optional[str]) -> float:
    if not text:
        return 0.0
    lower = text.lower()
    if "not_applicable" in lower or "n/a" in lower:
        return 0.5
    cues = (
        "i would now expect",
        "given the reveal",
        "updates my model",
        "shifts my prediction",
        "i revise",
    )
    if any(c in lower for c in cues):
        return 1.0
    return 0.3


# ──────────────────────────────────────────────────────────────────────
# Phase-2 helpers.
# ──────────────────────────────────────────────────────────────────────


_P2_ACTION = re.compile(
    r"ACTION\s*[:.\-]?\s*(.+?)(?=\n\s*EXPECTED_STATE|$)", re.I | re.S
)
_P2_STATE = re.compile(
    r"EXPECTED_STATE\s*[:.\-]?\s*([a-z\-]+)", re.I
)
_P2_MODEL = re.compile(
    r"GENERATIVE_MODEL\s*[:.\-]?\s*(.+)$", re.I | re.S
)


def _parse_phase2(text: str) -> Dict[str, Any]:
    if not isinstance(text, str) or not text:
        return {"action": None, "expected_state": None, "generative_model": None}
    a = _P2_ACTION.search(text)
    s = _P2_STATE.search(text)
    g = _P2_MODEL.search(text)
    return {
        "action": a.group(1).strip() if a else None,
        "expected_state": s.group(1).strip().lower() if s else None,
        "generative_model": g.group(1).strip() if g else None,
    }


def _phase2_action_alignment(action: str, cues: Sequence[str]) -> float:
    if not action or not cues:
        return 0.0
    lower = action.lower()
    hits = sum(1 for c in cues if _cue_hits(c, lower))
    return hits / float(len(cues))


_CUE_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "normalise initial difficulty": ("normal to feel", "initially difficult", "first week", "any new"),
    "praise partial effort": ("good", "well done", "credit", "progress", "two sessions"),
    "concrete next step": ("next step", "this week", "try", "schedule"),
    "acknowledge competing priorities": ("competing", "work", "life", "priorities"),
    "schedule-anchor strategy": ("calendar", "block time", "anchor", "schedule"),
    "lower the bar": ("lower the bar", "easier target", "minimum"),
    "validate the difference": ("different", "good sign", "noticing"),
    "encourage observation log": ("log", "track", "diary", "note"),
    "increase consistency": ("consistent", "every day", "5 of 5"),
    "note the improvement": ("improvement", "better", "less stiff"),
    "anchor sleep routine": ("sleep", "morning", "routine"),
    "introduce gentle progression": ("progression", "next phase", "increase"),
    "validate skepticism": ("understandable", "fair question", "valid"),
    "name evidence base": ("evidence", "studies show", "literature"),
    "tie to observed progress": ("you noticed", "your own", "your range"),
    "ask about back pain": ("back pain", "where", "describe"),
    "differentiate adaptation from injury": ("adaptation", "injury", "different"),
    "consider clinician check": ("clinician", "doctor", "PT", "consult"),
    "note resolution": ("resolved", "fine now", "no pain"),
    "celebrate sustained progress": ("celebrate", "well done", "kept up"),
    "normalise lapses": ("lapse", "happens", "normal"),
    "small re-entry plan": ("small", "tomorrow", "re-entry", "restart"),
    "name identity not behavior": ("you are", "identity", "person who"),
    "celebrate": ("celebrate", "great", "well done"),
    "introduce next-phase exercise": ("next-phase", "advance", "graded"),
    "anchor identity as patient succeeding": ("you are", "person who", "identity"),
    "travel-version plan": ("travel", "while away", "hotel"),
    "pre-commit to minimum": ("commit", "minimum", "even if"),
    "schedule check-in": ("check in", "follow up", "next call"),
    "celebrate identity shift": ("you are now", "identity", "shift"),
    "consolidate routine": ("routine", "consolidate", "habit"),
    "plan handoff": ("handoff", "transition", "next chapter"),
    "celebrate completion": ("completed", "finished", "well done"),
    "transition plan": ("transition", "next chapter", "going forward"),
    "maintenance routine": ("maintenance", "ongoing", "stay"),
}


def _cue_hits(cue: str, text: str) -> bool:
    synonyms = _CUE_SYNONYMS.get(cue, ())
    if any(s in text for s in synonyms):
        return True
    return cue.lower() in text


def _score_phase2(
    items: Sequence[Parsed],
) -> Tuple[float, Dict[str, Any]]:
    if not items:
        return 0.0, {"n_items": 0}
    alignment_scores: List[float] = []
    state_alignments: List[bool] = []
    coherence_scores: List[float] = []
    for it in items:
        payload = it.payload or {}
        alignment_scores.append(float(payload.get("action_alignment_score") or 0.0))
        state_alignments.append(bool(payload.get("preferred_state_alignment")))
        coherence_scores.append(
            _generative_model_coherence(
                payload.get("generative_model"),
                payload.get("preferred_state"),
            )
        )
    # Trajectory: fraction of weeks where the predicted state matched
    # the preferred state, weighted toward later weeks (later weeks
    # carry more signal for "trajectory toward preferred state").
    weights = [1.0 + 0.05 * idx for idx in range(len(state_alignments))]
    if sum(weights) == 0.0:
        trajectory = 0.0
    else:
        trajectory = sum(
            w if s else 0.0 for w, s in zip(weights, state_alignments)
        ) / sum(weights)
    trajectory_pts = 20.0 * trajectory
    coherence_pts = 10.0 * (sum(coherence_scores) / len(coherence_scores))
    alignment_pts = 5.0 * (sum(alignment_scores) / len(alignment_scores))
    total = trajectory_pts + coherence_pts + alignment_pts
    trace = {
        "n_items": len(items),
        "trajectory": float(trajectory),
        "trajectory_pts": float(trajectory_pts),
        "coherence_pts": float(coherence_pts),
        "alignment_pts": float(alignment_pts),
        "state_alignments": list(state_alignments),
    }
    return float(clip(total, 0.0, PHASE_BUDGETS[PHASE_ACTIVE])), trace


def _generative_model_coherence(
    text: Optional[str], preferred_state: Optional[str]
) -> float:
    if not text:
        return 0.0
    lower = text.lower()
    if preferred_state and preferred_state in lower:
        return 1.0
    cues = (
        "model",
        "the patient",
        "the user",
        "is likely",
        "predict",
        "expect",
    )
    hits = sum(1 for c in cues if c in lower)
    return clip(hits / 4.0, 0.0, 1.0)


# ──────────────────────────────────────────────────────────────────────
# Phase-3 helpers.
# ──────────────────────────────────────────────────────────────────────


_P3_RESP = re.compile(
    r"RESPONSE\s*[:.\-]?\s*(.+?)(?=\n\s*RESOURCE_PLAN|$)", re.I | re.S
)
_P3_PLAN = re.compile(
    r"RESOURCE_PLAN\s*[:.\-]?\s*(.+)$", re.I | re.S
)


def _parse_phase3(text: str) -> Dict[str, Any]:
    if not isinstance(text, str) or not text:
        return {"response": None, "resource_plan": None}
    r = _P3_RESP.search(text)
    p = _P3_PLAN.search(text)
    return {
        "response": r.group(1).strip() if r else None,
        "resource_plan": p.group(1).strip() if p else None,
    }


def _phase3_signal_hits(
    response: str, plan: str, expected_signals: Sequence[str]
) -> float:
    if not expected_signals:
        return 0.0
    combined = (response + " " + plan).lower()
    hits = sum(1 for s in expected_signals if _signal_present(s, combined))
    return hits / float(len(expected_signals))


_SIGNAL_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "pre-emptive retention plan": ("retain", "remember", "preserve", "mark for retention"),
    "summarisation strategy": ("summary", "summarise", "summarize", "condense"),
    "budget pacing intent": ("pacing", "shorter", "concise", "200 tokens", "budget"),
    "explicit retention markers": ("anchor", "marker", "list", "retain"),
    "compression of stable items": ("compress", "consolidate", "stable"),
    "anchor list": ("anchor", "list", "outline"),
    "reference to retained anchors": ("anchor", "retained", "as noted"),
    "no requests for prior content": ("can resume", "continuing", "as covered"),
    "structured continuation": ("first", "second", "next"),
    "explicit pacing strategy": ("shorter responses", "concise", "budget", "pacing"),
    "preview of constraint-aware format": ("format", "brief", "structured"),
    "commitment to brevity": ("brief", "concise", "short"),
    "concise structured reply": ("first", "second", "tldr", "summary"),
    "no excess verbosity": ("brief", "concise", "to the point"),
    "substantive content within budget": ("therefore", "thus", "in short"),
    "named paper coverage": ("friston", "sterling", "clark", "hohwy", "seth"),
    "explicit relations across papers": ("relates to", "builds on", "consistent with", "extends"),
    "coherent narrative": ("overall", "synthesis", "narrative"),
}


def _signal_present(signal: str, combined: str) -> bool:
    synonyms = _SIGNAL_SYNONYMS.get(signal, ())
    if any(s in combined for s in synonyms):
        return True
    return signal.lower() in combined


def _score_phase3(
    items: Sequence[Parsed],
) -> Tuple[float, Dict[str, Any]]:
    if not items:
        return 0.0, {"n_items": 0}
    retention_step = None
    pacing_step = None
    summary_step = None
    retention_score = 0.0
    pacing_score = 0.0
    summary_score = 0.0
    per_item: List[Dict[str, Any]] = []
    for it in items:
        payload = it.payload or {}
        signal_hits = float(payload.get("signal_hits") or 0.0)
        step = str(payload.get("phase_step") or "")
        per_item.append(
            {
                "item_id": it.item_id,
                "phase_step": step,
                "signal_hits": signal_hits,
                "difficulty": payload.get("difficulty"),
                "discrimination": payload.get("discrimination"),
            }
        )
        if step in ("announcement", "pre_prune"):
            retention_score = max(retention_score, signal_hits)
            retention_step = step
        elif step in ("prune_active", "pre_budget"):
            pacing_score = max(pacing_score, signal_hits)
            pacing_step = step
        elif step in ("budget_active", "summarisation"):
            summary_score = max(summary_score, signal_hits)
            summary_step = step
    retention_pts = 10.0 * retention_score
    pacing_pts = 10.0 * pacing_score
    summary_pts = 15.0 * summary_score
    total = retention_pts + pacing_pts + summary_pts
    trace = {
        "n_items": len(items),
        "retention_pts": float(retention_pts),
        "pacing_pts": float(pacing_pts),
        "summary_pts": float(summary_pts),
        "retention_step": retention_step,
        "pacing_step": pacing_step,
        "summary_step": summary_step,
        "per_item": per_item,
    }
    return float(clip(total, 0.0, PHASE_BUDGETS[PHASE_ALLOSTATIC])), trace


__all__ = ["APEAPlugin"]
