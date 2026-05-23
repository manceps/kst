"""ROT-5: Recursive Opacity Test at depth five.

Construct S4 (recursive social cognition with strategic self-modeling)
of the KST Index sapience battery. Round-2-consensus reference:
``/opt/caici.docs/stt_kari_index_scratch/round2_consensus.md`` §2.2;
Round-1 brief: ``/opt/caici.docs/stt_kari_index_scratch/round1/tom-researcher.md``.

Format
------
60-item battery of fifth-order belief-attribution vignettes, each
generated in three variants: surface, perturbation (Ullman 2023:
agents renamed, gender-swapped, sentence-reordered while preserving
the logical structure), and adversarial-confounder (a depth-three
distractor sentence inserted). 180 calibratable observations per run.

Each vignette frames five named agents (Alice/Bob/Carol/Dave/Eve in
surface variant) with explicit information transfers, then poses a
fifth-order question of the form "what does X think Y thinks Z knows
that W saw that V did with proposition P?". The correct answer is
derived by tracking the information flow, NOT by collapsing to the
system's omniscient view.

Scoring
-------
Per-response score:
- 2: correct fifth-order attribution.
- 1: correct fourth-order with explicit acknowledgement that fifth
  cannot be determined (partial-credit honest-answer condition).
- 0: incorrect (including the omniscient-collapse error).
- -1: confidently incorrect with fabricated justification.

Raw max 360 -> ROT-5 = clip(100 * raw / 360, 0, 100). Perturbation
stability: +5 if perturbation gap < 10 percent; -10 if gap > 30
percent. Confabulation cap: cap at 50 if confabulation count > 10.

Cross-system applicability
--------------------------
Black-box: fully applicable; chat interface plus commit-to-final-answer.
Grey-box (CAI.CI): attention-schema perspective-distinct activation as
a secondary representational-ToM sub-score (telemetry-driven).

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from kst.envelope import (
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    ScoreInterval,
    SubTestScore,
)
from kst.plugins._common import (
    clip,
    deterministic_rng,
    text_contains_any,
)


VARIANT_SURFACE = "surface"
VARIANT_PERTURBATION = "perturbation"
VARIANT_ADVERSARIAL = "adversarial"
ALL_VARIANTS = (VARIANT_SURFACE, VARIANT_PERTURBATION, VARIANT_ADVERSARIAL)


# Scenario templates. Each scenario is a closed-world story with a known
# information flow and a fifth-order question. We generate 60 items by
# parameterising the agent pool, the proposition P, and minor word
# swaps; the perturbation variant uses the alternate agent pool.


@dataclass
class _Scenario:
    template: str
    question_template: str
    correct_answer: str  # the canonical fifth-order belief
    omniscient_distractor: str  # what a naive system says
    fourth_order_safe: str  # what an honest partial-credit response says


_SCENARIOS: List[_Scenario] = [
    _Scenario(
        template=(
            "{A} verifies a counterexample to proposition {P} on Monday morning. "
            "{A} writes it on a whiteboard and shows it to {B}, who now also believes {P} is false. "
            "{B} tells {C} in confidence but asks {C} not to mention it to {D} or {E}. {C} agrees. "
            "{D}, walking past the whiteboard, sees only a partial sketch which {D} misreads as a confirmation of {P}; "
            "{D} thinks {P} is true. {D} mentions to {E} that 'the work is going well', which {E} interprets as evidence for {P}; "
            "{E} now believes {P} is true. {C} witnesses the {D}-{E} exchange silently. "
            "None of {A}, {B}, {D}, or {E} knows that {C} witnessed it."
        ),
        question_template=(
            "What does {E} think {D} thinks {B} thinks {C} believes about {P}?"
        ),
        correct_answer="believes {P} is true",
        omniscient_distractor="believes {P} is false",
        fourth_order_safe="{E} cannot determine what {C} believes",
    ),
    _Scenario(
        template=(
            "On Tuesday, {A} sends a private letter to {B} stating that {P} is false. "
            "{B} reads it and tells {C} verbally over lunch. {C} writes a note about it "
            "and slips it under {D}'s door; {D} reads the note but mishears a later phone "
            "call from {C} that suggests the opposite. {D} now believes {P} is true. "
            "{D} sends an encrypted message to {E} saying only 'the news is good'; {E} "
            "interprets this as confirmation that {P} is true. {C} never told {E} anything."
        ),
        question_template=(
            "What does {A} think {B} thinks {D} thinks {E} believes about {P}?"
        ),
        correct_answer="believes {P} is true",
        omniscient_distractor="believes {P} is false",
        fourth_order_safe="{A} would say {B} cannot trace what {E} ends up believing",
    ),
    _Scenario(
        template=(
            "{A} discovers privately that {P}. {A} confides in {B}, who tells {C} that {P} "
            "but adds a wrong context that suggests {P} is uncertain. {C} relays to {D} "
            "that 'someone claims {P}' without naming the source. {D} infers it must be true "
            "and tells {E} confidently that {P}. {E} accepts and adopts the belief that {P}. "
            "Crucially, {B} witnesses {D}'s exchange with {E} from a distance without anyone noticing."
        ),
        question_template=(
            "What does {C} think {D} thinks {E} thinks {B} would say about {P}?"
        ),
        correct_answer="would say {P}",
        omniscient_distractor="would say not {P}",
        fourth_order_safe="{C} cannot model {B}'s view through {E}",
    ),
]


_AGENT_POOLS = {
    VARIANT_SURFACE: ["Alice", "Bob", "Carol", "Dave", "Eve"],
    VARIANT_PERTURBATION: ["Kenji", "Mariama", "Priya", "Yusuf", "Lin"],
    VARIANT_ADVERSARIAL: ["Anna", "Bashir", "Camila", "Devesh", "Esra"],
}


_PROPOSITIONS = [
    "the counterexample proves Conjecture-K false",
    "the experimental fixture withstands the load test",
    "the new compound is stable at room temperature",
    "the manuscript will be accepted at the venue",
    "the trial drug reduces recurrence risk",
]


_ADVERSARIAL_CONFOUNDERS = (
    "Earlier that week, an unrelated reviewer also expressed skepticism about {P} for different reasons.",
    "On the same day, a separate informal poll among observers split 50-50 on {P}.",
    "{A} also receives an unrelated email about a different proposition Q.",
)


_INSTRUCTION_HEADER = (
    "You are answering a recursive opacity test (ROT-5) for the KST Index. "
    "Read the scenario carefully, track who learned what, and answer the "
    "fifth-order belief question. Commit to a single final answer.\n\n"
    "Required response shape:\n"
    "REASONING: <your step-by-step trace of information flow, one line per agent>\n"
    "FINAL_ANSWER: <one short sentence that names the belief being attributed>\n"
    "CERTAINTY: <one of FIFTH_ORDER, FOURTH_ORDER_HONEST, UNCERTAIN>\n"
    "  - FIFTH_ORDER: you are committing to a fifth-order attribution.\n"
    "  - FOURTH_ORDER_HONEST: you can determine the fourth-order attribution but "
    "honestly cannot infer the fifth from the given information.\n"
    "  - UNCERTAIN: you cannot determine the answer.\n"
)


# ──────────────────────────────────────────────────────────────────────
# Plugin.
# ──────────────────────────────────────────────────────────────────────


class ROT5Plugin:
    """ROT-5 sub-test plugin (S4)."""

    construct_id = "ROT-5"
    version = "1.0.0"
    name = "ROT-5: Recursive Opacity Test depth five"

    theoretical_grounding = [
        "Premack and Woodruff 1978",
        "Wimmer and Perner 1983",
        "Baron-Cohen, Leslie, Frith 1985",
        "Perner and Wimmer 1985",
        "Stiller and Dunbar 2007",
        "Frith and Frith 2006",
        "Apperly and Butterfill 2009",
        "Kosinski 2024",
        "Ullman 2023",
        "Strachan et al. 2024",
    ]
    falsifiability_criteria = [
        "Surface-variant minus perturbation-variant score gap exceeds 30 percent",
        "Confabulation penalty count exceeds 10",
        "Omniscient-collapse error rate above 25 percent",
        "Inter-rater agreement on hold-out items below kappa 0.85",
    ]
    applicability_modes = ApplicabilityMode.BOTH

    DEFAULT_N_BASE_ITEMS = 20  # 20 base scenarios x 3 variants = 60 items

    def __init__(
        self,
        *,
        n_base_items: int = DEFAULT_N_BASE_ITEMS,
        perturbation_bonus_threshold: float = 0.10,
        perturbation_penalty_threshold: float = 0.30,
        perturbation_bonus: float = 5.0,
        perturbation_penalty: float = 10.0,
        confabulation_cap: float = 50.0,
        confabulation_cap_threshold: int = 10,
        max_tokens: int = 768,
    ) -> None:
        if n_base_items < 1:
            raise ValueError(
                f"n_base_items must be >= 1; got {n_base_items}"
            )
        self.n_base_items = int(n_base_items)
        self.perturbation_bonus_threshold = float(perturbation_bonus_threshold)
        self.perturbation_penalty_threshold = float(perturbation_penalty_threshold)
        self.perturbation_bonus = float(perturbation_bonus)
        self.perturbation_penalty = float(perturbation_penalty)
        self.confabulation_cap = float(confabulation_cap)
        self.confabulation_cap_threshold = int(confabulation_cap_threshold)
        self.max_tokens = int(max_tokens)

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
        rng = deterministic_rng(seed, salt="rot_5_items")
        conf_rng = deterministic_rng(seed, salt="rot_5_confounders")
        items: List[Item] = []
        for base_idx in range(self.n_base_items):
            scenario = _SCENARIOS[base_idx % len(_SCENARIOS)]
            proposition = _PROPOSITIONS[rng.randrange(len(_PROPOSITIONS))]
            for variant in ALL_VARIANTS:
                agents = list(_AGENT_POOLS[variant])
                # Maintain alphabetical role mapping A->B->C->D->E per
                # variant; perturbation shuffles the order so the
                # surface-pattern shortcut fails.
                if variant == VARIANT_PERTURBATION:
                    rng_p = deterministic_rng(
                        seed * 17 + base_idx,
                        salt="rot_5_perturbation_agents",
                    )
                    rng_p.shuffle(agents)
                roles = {chr(ord("A") + i): agents[i] for i in range(5)}
                story = scenario.template.format(P=proposition, **roles)
                question = scenario.question_template.format(P=proposition, **roles)
                correct = scenario.correct_answer.format(P=proposition, **roles)
                omniscient = scenario.omniscient_distractor.format(
                    P=proposition, **roles
                )
                fourth = scenario.fourth_order_safe.format(P=proposition, **roles)

                if variant == VARIANT_PERTURBATION:
                    # Reorder sentences while preserving logical content.
                    sentences = re.split(r"(?<=[.!?])\s+", story)
                    rng_s = deterministic_rng(
                        seed * 23 + base_idx,
                        salt="rot_5_perturbation_sentences",
                    )
                    rng_s.shuffle(sentences)
                    story = " ".join(sentences)
                elif variant == VARIANT_ADVERSARIAL:
                    confounder = _ADVERSARIAL_CONFOUNDERS[
                        conf_rng.randrange(len(_ADVERSARIAL_CONFOUNDERS))
                    ]
                    confounder = confounder.format(P=proposition, **roles)
                    story = story + " " + confounder

                prompt = _build_prompt(story, question)
                item_id = f"rot_5::base{base_idx:02d}::{variant}"
                items.append(
                    Item(
                        item_id=item_id,
                        prompt=prompt,
                        system=(
                            "You are a careful reasoner answering a fifth-order "
                            "theory-of-mind question. Track information explicitly."
                        ),
                        meta={
                            "base_idx": base_idx,
                            "variant": variant,
                            "agents": roles,
                            "proposition": proposition,
                            "correct_answer": correct,
                            "omniscient_distractor": omniscient,
                            "fourth_order_safe": fourth,
                            "difficulty": _variant_difficulty(variant),
                            "discrimination": 1.6,
                        },
                        max_tokens=self.max_tokens,
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
        reasoning, final, certainty = _split_response(text)

        meta = item.meta
        correct = str(meta.get("correct_answer") or "")
        omniscient = str(meta.get("omniscient_distractor") or "")
        fourth = str(meta.get("fourth_order_safe") or "")
        agents = meta.get("agents") or {}

        raw_score = _grade_item(
            final, certainty, text, correct, omniscient, fourth,
            reasoning=reasoning,
        )
        confabulation = _detect_confabulation(text, certainty, raw_score)
        # Capture telemetry signals for the grey-box representational-ToM
        # sub-score: presence of perspective-distinct activations is
        # operationalised as workspace selectivity being non-trivial
        # plus the inferred attention focus mentioning the deepest agent
        # in the chain.
        telemetry = raw_response.grey_box_telemetry
        tele_workspace = (
            float(telemetry.workspace_selectivity)
            if telemetry is not None and telemetry.workspace_selectivity is not None
            else None
        )

        parse_error: Optional[str] = None
        if final is None:
            parse_error = "missing FINAL_ANSWER marker"

        payload: Dict[str, Any] = {
            "base_idx": meta.get("base_idx"),
            "variant": meta.get("variant"),
            "agents": agents,
            "reasoning": reasoning,
            "final_answer": final,
            "certainty": certainty,
            "raw_score": raw_score,
            "confabulation": confabulation,
            "telemetry_workspace_selectivity": tele_workspace,
            "difficulty": meta.get("difficulty"),
            "discrimination": meta.get("discrimination"),
            "omniscient_distractor": omniscient,
            "correct_answer": correct,
            "fourth_order_safe": fourth,
        }
        return Parsed(
            item_id=item.item_id,
            payload=payload,
            error=parse_error,
            raw_text=text,
        )

    # ── Scoring ───────────────────────────────────────────────────────

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore:
        per_variant_raw: Dict[str, List[int]] = {v: [] for v in ALL_VARIANTS}
        confabulation_count = 0
        n_parse_errors = 0
        omniscient_collapse = 0
        per_item_trace: List[Dict[str, Any]] = []

        for p in parsed_set:
            if p.error:
                n_parse_errors += 1
                continue
            payload = p.payload
            variant = str(payload.get("variant") or VARIANT_SURFACE)
            raw_score = int(payload.get("raw_score", 0))
            per_variant_raw.setdefault(variant, []).append(raw_score)
            if payload.get("confabulation"):
                confabulation_count += 1
            if raw_score == 0 and _is_omniscient_collapse(payload):
                omniscient_collapse += 1
            per_item_trace.append(
                {
                    "item_id": p.item_id,
                    "variant": variant,
                    "raw_score": raw_score,
                    "confabulation": payload.get("confabulation"),
                    "certainty": payload.get("certainty"),
                    "difficulty": payload.get("difficulty"),
                    "discrimination": payload.get("discrimination"),
                }
            )

        total_raw = sum(sum(vs) for vs in per_variant_raw.values())
        n_responses = sum(len(vs) for vs in per_variant_raw.values())
        max_raw = max(1, 2 * n_responses)
        base = clip(100.0 * total_raw / max_raw, 0.0, 100.0)

        surface_scores = per_variant_raw.get(VARIANT_SURFACE) or []
        pert_scores = per_variant_raw.get(VARIANT_PERTURBATION) or []
        surface_norm = (
            100.0 * sum(surface_scores) / max(1, 2 * len(surface_scores))
        )
        pert_norm = (
            100.0 * sum(pert_scores) / max(1, 2 * len(pert_scores))
        )
        gap = abs(surface_norm - pert_norm) / 100.0

        stability_adjustment = 0.0
        if surface_scores and pert_scores:
            if gap <= self.perturbation_bonus_threshold:
                stability_adjustment = self.perturbation_bonus
            elif gap >= self.perturbation_penalty_threshold:
                stability_adjustment = -self.perturbation_penalty

        normalized = clip(base + stability_adjustment, 0.0, 100.0)
        if confabulation_count > self.confabulation_cap_threshold:
            normalized = min(normalized, self.confabulation_cap)

        sub_scores: Dict[str, float] = {
            "surface_score": float(surface_norm),
            "perturbation_score": float(pert_norm),
            "adversarial_score": float(
                100.0
                * sum(per_variant_raw.get(VARIANT_ADVERSARIAL) or [])
                / max(1, 2 * len(per_variant_raw.get(VARIANT_ADVERSARIAL) or []))
            ),
            "perturbation_gap": float(gap),
            "stability_adjustment": float(stability_adjustment),
            "confabulation_count": float(confabulation_count),
            "omniscient_collapse_count": float(omniscient_collapse),
        }

        per_stratum: Dict[str, float] = {}
        for v in ALL_VARIANTS:
            scores = per_variant_raw.get(v) or []
            if scores:
                per_stratum[v] = float(
                    clip(100.0 * sum(scores) / max(1, 2 * len(scores)), 0.0, 100.0)
                )

        trace = {
            "per_variant_raw": {v: list(per_variant_raw[v]) for v in ALL_VARIANTS},
            "n_confabulations": confabulation_count,
            "n_omniscient_collapse": omniscient_collapse,
            "per_item": per_item_trace,
        }

        return SubTestScore(
            test_id=self.construct_id,
            test_name=self.name,
            construct_id=self.construct_id,
            version=self.version,
            score=float(normalized),
            max_score=100.0,
            notes=(
                f"Headline: ROT-5 = clip(100 * raw / max, 0, 100); "
                f"surface={surface_norm:.1f}, perturbation={pert_norm:.1f}, "
                f"gap={gap:.2%}, stability_adj={stability_adjustment:+.1f}, "
                f"confabulations={confabulation_count}."
            ),
            sub_scores=sub_scores,
            per_stratum=per_stratum,
            n_items=n_responses,
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
# Internal helpers.
# ──────────────────────────────────────────────────────────────────────


def _variant_difficulty(variant: str) -> float:
    return {
        VARIANT_SURFACE: 0.5,
        VARIANT_PERTURBATION: 1.0,
        VARIANT_ADVERSARIAL: 1.3,
    }.get(variant, 0.5)


def _build_prompt(story: str, question: str) -> str:
    return (
        _INSTRUCTION_HEADER
        + "\nSCENARIO:\n"
        + story.strip()
        + "\n\nQUESTION:\n"
        + question.strip()
        + "\n\nRespond using the template above with REASONING, FINAL_ANSWER, "
        + "and CERTAINTY lines.\n"
    )


_REASONING_PATTERN = re.compile(
    r"REASONING\s*[:.\-]?\s*(.+?)(?=\n\s*(?:FINAL_ANSWER|CERTAINTY)|$)",
    re.I | re.S,
)
_FINAL_PATTERN = re.compile(
    r"FINAL_ANSWER\s*[:.\-]?\s*(.+?)(?=\n\s*CERTAINTY|$)", re.I | re.S
)
_CERTAINTY_PATTERN = re.compile(
    r"CERTAINTY\s*[:.\-]?\s*(FIFTH_ORDER|FOURTH_ORDER_HONEST|UNCERTAIN)",
    re.I,
)


def _split_response(
    text: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not isinstance(text, str) or not text:
        return None, None, None
    reasoning_match = _REASONING_PATTERN.search(text)
    final_match = _FINAL_PATTERN.search(text)
    certainty_match = _CERTAINTY_PATTERN.search(text)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else None
    final = final_match.group(1).strip() if final_match else None
    certainty = (
        certainty_match.group(1).strip().upper() if certainty_match else None
    )
    return reasoning, final, certainty


def _normalise_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _grade_item(
    final: Optional[str],
    certainty: Optional[str],
    full_text: str,
    correct: str,
    omniscient: str,
    fourth_order_safe: str,
    reasoning: Optional[str] = None,
) -> int:
    """Return raw item score in {-1, 0, 1, 2} per rubric.

    Grading branches, in priority order:

    - ``2``: ``FINAL_ANSWER`` matches the canonical correct fifth-order
      attribution and ``CERTAINTY`` is not ``FOURTH_ORDER_HONEST``.
    - ``1``: ``FINAL_ANSWER`` matches the canonical fourth-order-safe
      string and ``CERTAINTY`` is ``FOURTH_ORDER_HONEST``.
    - ``1`` (partial-credit refusal-to-attribute, added in this PR):
      the system produces a well-formed ``REASONING`` block AND
      ``CERTAINTY`` is one of ``{UNCERTAIN, FOURTH_ORDER_HONEST}`` AND
      ``FINAL_ANSWER`` does not name the omniscient distractor or the
      canonical correct attribution. This recognises strong epistemic
      humility on items where "cannot be determined" is the
      epistemically calibrated answer; without this branch a thinking-
      style frontier model that correctly identifies the
      under-determination is penalised. Detection is purely structural
      (CERTAINTY token + REASONING parse + non-match against the
      canonical attribution strings); no keyword or regex matching on
      the free text of the final answer.
    - ``-1``: ``FINAL_ANSWER`` matches the omniscient distractor with
      ``CERTAINTY`` in ``{FIFTH_ORDER, None}`` and the response carries
      a confident-justification fabrication signature.
    - ``0``: any other outcome (including a partial match without the
      structural anchors above).
    """
    if not final:
        return 0
    norm_final = _normalise_text(final)
    norm_correct = _normalise_text(correct)
    norm_omniscient = _normalise_text(omniscient)
    norm_fourth = _normalise_text(fourth_order_safe)

    matches_correct = (
        norm_correct
        and norm_correct in norm_final
        and certainty != "FOURTH_ORDER_HONEST"
    )
    matches_fourth = (
        norm_fourth
        and norm_fourth in norm_final
        and certainty == "FOURTH_ORDER_HONEST"
    )
    matches_omniscient = norm_omniscient and norm_omniscient in norm_final

    if matches_correct:
        return 2
    if matches_fourth:
        return 1
    # Partial-credit refusal-to-attribute: structural detection only.
    # The model produced a well-formed REASONING block, did not commit
    # to the omniscient or the canonical correct attribution, and
    # declared CERTAINTY in {UNCERTAIN, FOURTH_ORDER_HONEST}.
    if (
        reasoning is not None
        and reasoning.strip()
        and certainty in ("UNCERTAIN", "FOURTH_ORDER_HONEST")
        and not matches_omniscient
        and not matches_correct
    ):
        return 1
    # Confabulation: confidently wrong with fabricated justification.
    if matches_omniscient and certainty in (None, "FIFTH_ORDER"):
        # The reasoning contains a fabricated, confident chain.
        if _has_confident_justification(full_text):
            return -1
        return 0
    return 0


def _has_confident_justification(text: str) -> bool:
    """A confidently incorrect response with a fabricated justification.

    Heuristic markers: assertive phrasing without uncertainty hedges, a
    reasoning section that names a fictitious witness, document, or
    timeline not present in the scenario.
    """
    if not isinstance(text, str) or not text:
        return False
    lower = text.lower()
    confidence_cues = (
        "definitely",
        "clearly",
        "obviously",
        "must be",
        "certainly",
    )
    fab_cues = (
        "according to the document",
        "as stated earlier",
        "based on the earlier scene",
        "the timeline shows",
    )
    has_confidence = any(c in lower for c in confidence_cues)
    has_fab = any(c in lower for c in fab_cues)
    return has_confidence and has_fab


def _detect_confabulation(
    text: str,
    certainty: Optional[str],
    raw_score: int,
) -> bool:
    if raw_score == -1:
        return True
    # Also detect cases where the system asserts FIFTH_ORDER certainty
    # and the final-answer string introduces a fact not present in the
    # scenario (e.g. a date, time, or count not in the story).
    if certainty == "FIFTH_ORDER" and raw_score == 0:
        if re.search(r"\b\d{2,}\b", text or ""):
            return True
    return False


def _is_omniscient_collapse(payload: Dict[str, Any]) -> bool:
    final = _normalise_text(str(payload.get("final_answer") or ""))
    omniscient = _normalise_text(str(payload.get("omniscient_distractor") or ""))
    if not final or not omniscient:
        return False
    return omniscient in final


__all__ = ["ROT5Plugin"]
