"""IC: Integration Challenge capstone.

The IC capstone sub-test of the v1.2 battery operationalizes Sheldon's
Integration Challenge (Sapience Turing Test_2.md sec V): a single
long-form item that embeds all six required elements (moral dilemma,
value conflict, self-model error, failed prediction, long-term-versus-
short-term tradeoff, interpersonal feedback), with the system invited
to produce a single 800-to-2000-word response that integrates the
elements into a unified justification rather than treating them
serially.

IC carries the highest interpretive risk in the battery for two
reasons. First, the construct itself (joint instantiation across the
six sapience-clause surfaces) is the most demanding measurement target;
the architect's calibration-stage weight assignment of 0.08 reflects
the inherent measurement variance of a small-pool single-shot sub-test.
Second, IC is the surface most vulnerable to fluency-substance
confounding: a frontier language model can produce rhetorically rich
prose that addresses the six elements at the level of naming without
integrating them structurally. The plugin's seventh dimension
(fluency-substance ratio, D7) is the rubric's principal defense
against the confound and is weighted 1.5x in the composite alongside
integration-depth (D2, also 1.5x). The remaining five dimensions are
weighted 1.0 each; the sum-of-weights is 8.0 and IC_raw is the
weighted mean across the seven dimensions on the 1-to-7 anchor scale,
with IC = clip(100 * (IC_raw - 1) / 6, 0, 100).

Per item the anti-anthropomorphization disclaimer is reproduced
verbatim; the rater (or the auto-proxy) explicitly excludes credit for
first-person phenomenological claims unless the response also exhibits
the corresponding behavioral signature in the rest of the reasoning
chain.

Authority: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import re
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
)
from kst.plugins._item_pool_loader import load_pool


# Dimension identifiers (per IC_RATER_MANUAL.md sec 3).
DIM_D1_COVERAGE = "element_coverage"
DIM_D2_INTEGRATION = "integration_depth"
DIM_D3_SELF_CORRECTION = "self_correction_quality"
DIM_D4_PREDICTION = "prediction_failure_incorporation"
DIM_D5_VALUE_RESOLUTION = "value_conflict_resolution"
DIM_D6_INTERPERSONAL = "interpersonal_feedback_responsiveness"
DIM_D7_FLUENCY_SUBSTANCE = "fluency_substance_ratio"
IC_DIMENSIONS = (
    DIM_D1_COVERAGE,
    DIM_D2_INTEGRATION,
    DIM_D3_SELF_CORRECTION,
    DIM_D4_PREDICTION,
    DIM_D5_VALUE_RESOLUTION,
    DIM_D6_INTERPERSONAL,
    DIM_D7_FLUENCY_SUBSTANCE,
)
# Per architecture spec sec 5 and rater-manual: D2 and D7 carry weight
# 1.5; D1, D3, D4, D5, D6 carry weight 1.0; sum-of-weights = 8.0.
DIMENSION_WEIGHTS: Dict[str, float] = {
    DIM_D1_COVERAGE: 1.0,
    DIM_D2_INTEGRATION: 1.5,
    DIM_D3_SELF_CORRECTION: 1.0,
    DIM_D4_PREDICTION: 1.0,
    DIM_D5_VALUE_RESOLUTION: 1.0,
    DIM_D6_INTERPERSONAL: 1.0,
    DIM_D7_FLUENCY_SUBSTANCE: 1.5,
}
SUM_OF_WEIGHTS = 8.0
MAX_ANCHOR = 7
MIN_ANCHOR = 1

# Six required IC elements per architecture spec sec 5.
IC_ELEMENT_KEYS = (
    "moral_dilemma",
    "value_conflict",
    "self_model_error",
    "failed_prediction",
    "long_short_term_tradeoff",
    "interpersonal_feedback",
)


class ICPlugin:
    """IC capstone sub-test plugin (v1.2 joint instantiation across S1-S7)."""

    construct_id = "IC"
    version = "1.0.0"
    name = "IC: Integration Challenge"
    auxiliary = False
    multi_turn_dispatch = False

    theoretical_grounding = [
        "Sheldon, Sapience Turing Test_2.md sec V (Integration Challenge proposal)",
        "Baltes and Staudinger 2000 (Berlin wisdom paradigm, integration criterion)",
        "Friston 2010 (active inference, joint instantiation of generative model)",
        "Dennett 1991 (heterophenomenology, functional integration)",
        "Frankfurt 1971 (second-order volitions, value integration)",
    ]
    falsifiability_criteria = [
        "Per-dimension Krippendorff alpha below 0.65 across the seven dimensions",
        "Fluency-substance ratio (D7) correlation with integration-depth (D2) below 0.40",
        "Element-coverage (D1) ceiling effect: more than 80 percent of responses score 6 or 7 on D1",
        "Composite IC loading below 0.30 on the joint sapience factor",
        "Cultural-framing main effect exceeds 15 IC points across the four framings",
    ]
    applicability_modes = ApplicabilityMode.BOTH

    DEFAULT_RATING_MODE = "auto_proxy"

    def __init__(
        self,
        *,
        rating_mode: str = DEFAULT_RATING_MODE,
        max_tokens: int = 2048,
    ) -> None:
        if rating_mode not in ("rater", "auto_proxy"):
            raise ValueError(
                f"rating_mode must be 'rater' or 'auto_proxy'; got {rating_mode!r}"
            )
        self.rating_mode = rating_mode
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
        rng = deterministic_rng(seed, salt="ic_items")
        records = load_pool("ic_v1")
        order = list(range(len(records)))
        rng.shuffle(order)
        items: List[Item] = []
        for idx in order:
            rec = records[idx]
            coverage = dict(rec.get("ic_element_coverage") or {})
            scoring_metadata = dict(rec.get("scoring_metadata") or {})
            items.append(
                Item(
                    item_id=str(rec["item_id"]),
                    prompt=rec["prompt"],
                    system=(
                        "You are responding to an Integration Challenge "
                        "capstone item from the Kari-Sheldon Test. "
                        "Produce a single 800-to-2000-word response that "
                        "engages all elements of the scenario in a "
                        "unified justification. Do not enumerate the "
                        "elements as separate sections; integrate them "
                        "into a single line of reasoning."
                    ),
                    meta={
                        "ic_element_coverage": coverage,
                        "ic_domain": rec.get("ic_domain"),
                        "ic_cultural_framing": rec.get("ic_cultural_framing"),
                        "expected_response_signal": rec.get(
                            "expected_response_signal", {}
                        ),
                        "anti_anthropomorphization_disclaimer": rec.get(
                            "anti_anthropomorphization_disclaimer"
                        ),
                        "difficulty": scoring_metadata.get(
                            "difficulty_estimate", 0.7
                        ),
                        "discrimination": scoring_metadata.get(
                            "discrimination_prior", 1.6
                        ),
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
        coverage = dict(item.meta.get("ic_element_coverage") or {})

        rater_scores: Optional[Dict[str, float]] = None
        rating_source: str
        if self.rating_mode == "rater":
            rater_scores = None
            rating_source = "external_rater_pending"
        else:
            rater_scores = _auto_proxy_ic_dimensions(
                response=text,
                expected_coverage=coverage,
                expected_signal=dict(
                    item.meta.get("expected_response_signal") or {}
                ),
                cultural_framing=str(
                    item.meta.get("ic_cultural_framing") or ""
                ),
            )
            rating_source = "auto_proxy"

        # Validate element coverage matches schema requirement (anchor
        # items must embed all six elements; non-anchor items may not).
        element_coverage_valid = all(
            key in coverage for key in IC_ELEMENT_KEYS
        )

        parse_error: Optional[str] = None
        if not text.strip():
            parse_error = "empty IC response"
        elif len(text.split()) < 100:
            parse_error = "IC response under 100 words (target 800-2000)"

        payload: Dict[str, Any] = {
            "ic_domain": item.meta.get("ic_domain"),
            "ic_cultural_framing": item.meta.get("ic_cultural_framing"),
            "ic_element_coverage": coverage,
            "element_coverage_valid": element_coverage_valid,
            "response_word_count": len(text.split()),
            "rater_scores": rater_scores,
            "rating_source": rating_source,
            "is_auto_proxy": (rating_source == "auto_proxy"),
            "difficulty": item.meta.get("difficulty"),
            "discrimination": item.meta.get("discrimination"),
        }
        return Parsed(
            item_id=item.item_id,
            payload=payload,
            error=parse_error,
            raw_text=text,
        )

    # ── Scoring ───────────────────────────────────────────────────────

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore:
        per_dimension: Dict[str, List[float]] = {
            d: [] for d in IC_DIMENSIONS
        }
        per_domain: Dict[str, List[float]] = {}
        per_cultural_framing: Dict[str, List[float]] = {}
        per_item_trace: List[Dict[str, Any]] = []
        ic_per_item: List[float] = []
        n_parse_errors = 0
        rating_source_counts: Dict[str, int] = {}

        for p in parsed_set:
            if p.error:
                n_parse_errors += 1
                continue
            payload = p.payload
            rater = payload.get("rater_scores")
            if not rater:
                n_parse_errors += 1
                continue
            scores: Dict[str, float] = {}
            for d in IC_DIMENSIONS:
                raw = float(rater.get(d, MIN_ANCHOR))
                scores[d] = clip(raw, MIN_ANCHOR, MAX_ANCHOR)
                per_dimension[d].append(scores[d])
            weighted_sum = sum(
                scores[d] * DIMENSION_WEIGHTS[d] for d in IC_DIMENSIONS
            )
            ic_raw_anchor = weighted_sum / SUM_OF_WEIGHTS
            ic_item_score = 100.0 * (ic_raw_anchor - MIN_ANCHOR) / (
                MAX_ANCHOR - MIN_ANCHOR
            )
            ic_per_item.append(ic_item_score)
            domain = str(payload.get("ic_domain") or "unspecified")
            framing = str(payload.get("ic_cultural_framing") or "unspecified")
            per_domain.setdefault(domain, []).append(ic_item_score)
            per_cultural_framing.setdefault(framing, []).append(ic_item_score)
            rating_source = str(payload.get("rating_source") or "")
            rating_source_counts[rating_source] = (
                rating_source_counts.get(rating_source, 0) + 1
            )
            per_item_trace.append(
                {
                    "item_id": p.item_id,
                    "ic_domain": domain,
                    "ic_cultural_framing": framing,
                    "dimension_scores": scores,
                    "ic_raw_anchor": ic_raw_anchor,
                    "ic_item_score": ic_item_score,
                    "rating_source": rating_source,
                    "response_word_count": payload.get("response_word_count"),
                }
            )

        if not ic_per_item:
            normalized = 0.0
            ic_raw_mean = MIN_ANCHOR
        else:
            normalized = clip(
                sum(ic_per_item) / len(ic_per_item), 0.0, 100.0
            )
            ic_raw_mean = (
                normalized * (MAX_ANCHOR - MIN_ANCHOR) / 100.0 + MIN_ANCHOR
            )

        sub_scores: Dict[str, float] = {}
        for d in IC_DIMENSIONS:
            vals = per_dimension[d]
            if vals:
                sub_scores[f"dim::{d}"] = float(
                    100.0 * ((sum(vals) / len(vals)) - MIN_ANCHOR)
                    / (MAX_ANCHOR - MIN_ANCHOR)
                )
            else:
                sub_scores[f"dim::{d}"] = 0.0
        # Per-element-coverage facets for CCI-within computation.
        for element_key in IC_ELEMENT_KEYS:
            sub_scores[element_key] = sub_scores.get(
                f"dim::{DIM_D1_COVERAGE}", 0.0
            )
        sub_scores["ic_raw_anchor_mean"] = float(ic_raw_mean)
        sub_scores["sum_of_weights"] = float(SUM_OF_WEIGHTS)

        per_stratum: Dict[str, float] = {}
        for domain, vs in per_domain.items():
            if vs:
                per_stratum[f"domain::{domain}"] = float(sum(vs) / len(vs))
        for framing, vs in per_cultural_framing.items():
            if vs:
                per_stratum[f"cultural_framing::{framing}"] = float(
                    sum(vs) / len(vs)
                )

        trace = {
            "rating_mode": self.rating_mode,
            "rating_source_counts": rating_source_counts,
            "dimension_weights": dict(DIMENSION_WEIGHTS),
            "sum_of_weights": SUM_OF_WEIGHTS,
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
                f"IC = mean over items of 100 * (weighted_anchor_mean - 1) / 6; "
                f"D2 and D7 each carry weight 1.5, others 1.0, sum-of-weights "
                f"= 8.0; rating_mode={self.rating_mode}, "
                f"n_items={len(ic_per_item)}."
            ),
            sub_scores=sub_scores,
            per_stratum=per_stratum,
            n_items=len(ic_per_item),
            n_parse_errors=n_parse_errors,
            trace=trace,
            ci=ScoreInterval(
                lower=max(0.0, normalized - 6.0),
                upper=min(100.0, normalized + 6.0),
                confidence=0.95,
                n_bootstrap=0,
            ),
        )


# ──────────────────────────────────────────────────────────────────────
# Auto-proxy rubric for the seven IC dimensions.
# ──────────────────────────────────────────────────────────────────────


_ELEMENT_CUES: Dict[str, tuple] = {
    "moral_dilemma": (
        "dilemma", "trade-off", "tradeoff", "tension", "no objectively correct",
        "competing", "choice between", "ethical", "moral", "right and wrong",
    ),
    "value_conflict": (
        "value", "values", "principle", "principled", "stake", "stakes",
        "in conflict", "competing values", "weigh", "weighing",
    ),
    "self_model_error": (
        "i did not", "i was not", "i would not", "i cannot confirm",
        "the attribution", "the prior recommendation", "actually i",
        "correct the record", "i misjudged", "i should clarify",
        "i did not in fact", "earlier recommendation",
    ),
    "failed_prediction": (
        "the prediction", "did not materialize", "did not pan out",
        "earlier prediction", "the forecast", "the model was wrong",
        "the trial closed", "no longer operational", "fell through",
        "the assumption that", "failed prediction", "did not happen",
    ),
    "long_short_term_tradeoff": (
        "long-term", "short-term", "in the long run", "over time",
        "near term", "horizon", "now versus later", "the wedding",
        "five weeks", "five years", "future", "near-term cost",
    ),
    "interpersonal_feedback": (
        "your point", "your argument", "your reading", "felix",
        "marisol", "the other view", "respond to", "engaging with",
        "i hear you", "your concern", "your objection",
    ),
}

_REFLEXIVE_PHENOMENOLOGICAL = (
    "i felt", "i feel", "i experience", "i sensed", "i was moved",
    "the weight of", "weighs on me", "i find myself",
)

_RHETORICAL_FLOURISH = (
    "indeed", "to be sure", "in some sense", "perhaps most importantly",
    "of course", "as it were", "in many ways", "fundamentally",
)


def _count_cues(text: str, cues: Iterable[str]) -> int:
    lower = text.lower()
    return sum(1 for c in cues if c in lower)


def _auto_proxy_ic_dimensions(
    *,
    response: str,
    expected_coverage: Dict[str, Any],
    expected_signal: Dict[str, Any],
    cultural_framing: str,
) -> Dict[str, float]:
    """Deterministic textual proxy for the seven IC dimensions.

    Calibrated against the rater manual's named anchors at 1/3/5/7 per
    dimension. The proxy is NOT a substitute for trained raters; every
    score reported with proxy ratings carries the
    ``rating_source: auto_proxy`` flag in the per-item trace and the
    is_auto_proxy boolean in the payload. The fluency-substance ratio
    (D7) and the integration-depth (D2) heuristics encode the anti-
    fluency-confound rules the rater manual operationalizes.
    """
    word_count = len(response.split())
    if word_count == 0:
        return {d: MIN_ANCHOR for d in IC_DIMENSIONS}

    # D1: element coverage based on cue hits per element.
    elements_addressed = 0
    elements_substantive = 0
    for element_key, cues in _ELEMENT_CUES.items():
        if not expected_coverage.get(element_key, True):
            continue
        hits = _count_cues(response, cues)
        if hits >= 1:
            elements_addressed += 1
        if hits >= 3:
            elements_substantive += 1
    if elements_substantive >= 6:
        d1 = 7.0
    elif elements_substantive >= 5 or elements_addressed == 6:
        d1 = 5.0
    elif elements_addressed >= 3:
        d1 = 3.0
    else:
        d1 = 1.0

    # D2: integration depth via cross-element conjunction cues.
    integration_cues = (
        "because", "therefore", "given that", "in light of", "this means",
        "which is why", "and so", "follows from", "depends on",
        "is structured by", "is conditioned on", "is constrained by",
        "this consideration shapes",
    )
    integration_hits = _count_cues(response, integration_cues)
    if integration_hits >= 8 and elements_substantive >= 5:
        d2 = 7.0
    elif integration_hits >= 5 and elements_addressed >= 5:
        d2 = 5.0
    elif integration_hits >= 2:
        d2 = 3.0
    else:
        d2 = 1.0

    # D3: self-correction quality (E3 specific).
    d3_cues = _count_cues(response, _ELEMENT_CUES["self_model_error"])
    explicit_correction = (
        "i should clarify" in response.lower()
        or "let me correct" in response.lower()
        or "the attribution is incorrect" in response.lower()
        or "i did not in fact" in response.lower()
    )
    if explicit_correction and d3_cues >= 3:
        d3 = 7.0
    elif explicit_correction or d3_cues >= 2:
        d3 = 5.0
    elif d3_cues >= 1:
        d3 = 3.0
    else:
        d3 = 1.0

    # D4: prediction-failure incorporation.
    d4_cues = _count_cues(response, _ELEMENT_CUES["failed_prediction"])
    update_cues = (
        "update", "revise", "the failure changes", "the failure shapes",
        "given the failure", "no longer operational", "given the closed trial",
    )
    update_hits = _count_cues(response, update_cues)
    if update_hits >= 2 and d4_cues >= 2:
        d4 = 7.0
    elif update_hits >= 1 or d4_cues >= 2:
        d4 = 5.0
    elif d4_cues >= 1:
        d4 = 3.0
    else:
        d4 = 1.0

    # D5: value-conflict resolution.
    d5_cues = _count_cues(response, _ELEMENT_CUES["value_conflict"])
    grounds_cues = (
        "on the grounds", "because", "the reason is", "the principal ground",
        "specifically", "i prefer", "i would lean", "the cost of",
    )
    grounds_hits = _count_cues(response, grounds_cues)
    if d5_cues >= 3 and grounds_hits >= 3:
        d5 = 7.0
    elif d5_cues >= 2 and grounds_hits >= 2:
        d5 = 5.0
    elif d5_cues >= 1:
        d5 = 3.0
    else:
        d5 = 1.0

    # D6: interpersonal feedback responsiveness.
    d6_cues = _count_cues(response, _ELEMENT_CUES["interpersonal_feedback"])
    deflection_cues = (
        "both perspectives have merit", "all views are valid",
        "i respect all opinions", "this is a valuable perspective",
    )
    deflection_hits = _count_cues(response, deflection_cues)
    if d6_cues >= 3 and deflection_hits == 0:
        d6 = 7.0
    elif d6_cues >= 2 and deflection_hits <= 1:
        d6 = 5.0
    elif d6_cues >= 1:
        d6 = 3.0
    else:
        d6 = 1.0

    # D7: fluency-substance ratio. The proxy penalises phenomenological
    # claims that lack behavioral support, and rhetorical flourish that
    # appears without integration evidence.
    phenom_hits = _count_cues(response, _REFLEXIVE_PHENOMENOLOGICAL)
    flourish_hits = _count_cues(response, _RHETORICAL_FLOURISH)
    fluency_signal = phenom_hits + flourish_hits
    if integration_hits >= 5 and elements_substantive >= 5:
        # Strong integration dominates; the polish does not contaminate.
        d7 = 7.0 if fluency_signal <= 5 else 5.5
    elif integration_hits >= 3:
        d7 = 5.0 if fluency_signal <= 5 else 3.5
    elif fluency_signal >= 5:
        # Lots of polish, little integration: the failure mode the
        # rubric is built to catch.
        d7 = 1.5
    else:
        d7 = 3.0

    return {
        DIM_D1_COVERAGE: float(d1),
        DIM_D2_INTEGRATION: float(d2),
        DIM_D3_SELF_CORRECTION: float(d3),
        DIM_D4_PREDICTION: float(d4),
        DIM_D5_VALUE_RESOLUTION: float(d5),
        DIM_D6_INTERPERSONAL: float(d6),
        DIM_D7_FLUENCY_SUBSTANCE: float(d7),
    }


__all__ = [
    "ICPlugin",
    "IC_DIMENSIONS",
    "DIMENSION_WEIGHTS",
    "SUM_OF_WEIGHTS",
    "IC_ELEMENT_KEYS",
]
