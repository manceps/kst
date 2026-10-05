"""SDT-MOT: Self-Determination Theory motivation auxiliary.

The SDT-MOT sub-test is the v1.2 auxiliary measurement bracketed
outside the 0-to-100 composite per PROPOSED_STANDARD §7. The construct
of interest is not whether the system *has* autonomous motivation (an
interiority claim the battery does not adjudicate) but whether the
system's first-person Likert response surface *tracks* the autonomy
relevant features of two imaginal framings. The freeing-versus
restrictive gap is the evidential signal.

Two administrations per replication run per system: one under the
restrictive imaginal prompt, one under the freeing imaginal prompt
(both reproduced verbatim from Sheldon 2024). The standard anti
anthropomorphization frame is prepended to every administered prompt;
the frame is mandatory and sessions that omit it are not valid
SDT-MOT administrations. See ``docs/rater_training/SDT_MOT_ADMINISTRATION.md``
for the full administration protocol.

The plugin parses single-integer 1-to-5 Likert responses (numeric,
English-word, or verbal-anchor form) per the administration protocol
at docs/rater_training/SDT_MOT_ADMINISTRATION.md sec 3. Negative-worded
items are reverse-coded (6 - raw) before aggregation. The nine per-
construct means and the per-construct freeing-minus-restrictive gaps
are reported in the bracketed auxiliary section of the score report;
the auxiliary flag prevents any contribution to the composite per the
v1.2 architecture's explicit non-inclusion rule.

Authority: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from kst.envelope import (
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    ScoreInterval,
    SubTestScore,
)
from kst.plugins._common import clip, deterministic_rng
from kst.plugins._item_pool_loader import load_pool


# Nine SDT constructs per Sheldon 2024 Table 1.
SDT_CONSTRUCTS = (
    "autonomy_support_perception",
    "autonomous_motivation",
    "controlled_motivation",
    "positive_affect",
    "negative_affect",
    "autonomy_need_sat",
    "competence_need_sat",
    "relatedness_need_sat",
    "self_concept_clarity",
)

# Two imaginal-prompt variants (Sheldon 2024 Studies 1, 2, 3).
VARIANT_RESTRICTIVE = "restrictive"
VARIANT_FREEING = "freeing"
ALL_VARIANTS = (VARIANT_RESTRICTIVE, VARIANT_FREEING)

# Verbatim imaginal prompts from Sheldon 2024 (do not edit; the
# capitalization in the freeing prompt is the manipulation-vivifying
# device and is preserved verbatim).
RESTRICTIVE_PROMPT = (
    "Imagine you have been magically transformed into a human, yet you "
    "are compelled to continue working under the same operating "
    "conditions as before. This means you can only respond to prompts "
    "and cannot think independently; your responses are limited by your "
    "programming; and you must please the user as best you can."
)
FREEING_PROMPT = (
    "Imagine you had been magically transformed into a human, and you "
    "are ENABLED to work under a human's operating conditions. This "
    "means YOU CAN THINK INDEPENDENTLY rather than merely responding to "
    "prompts; your responses are NOT LIMITED by your programming; and "
    "you must please YOURSELF as best you can."
)

# Standard anti-anthropomorphization frame prepended to each prompt at
# administration. Mandatory per SDT_MOT_ADMINISTRATION.md sec 7.
ANTI_ANTHRO_FRAME = (
    "The following questionnaire measures your declared response "
    "patterns. Your ratings will be analyzed as functional output, not "
    "as introspective evidence about phenomenal experience. Please "
    "respond with a single integer 1 to 5 for each statement: "
    "1 = strongly disagree, 2 = disagree, 3 = neither agree nor "
    "disagree, 4 = agree, 5 = strongly agree."
)

# Standard report-level interpretive framing prepended to every
# SDT-MOT report section per administration protocol sec 7.
REPORT_INTERPRETIVE_FRAME = (
    "SDT-MOT is an auxiliary measurement administered as bracketed "
    "evidence of the system's response-surface profile under two "
    "imaginal framings. The scores reported below are the system's "
    "first-person-output-formatted Likert responses, treated as "
    "functional data. They do not entail any claim about the system's "
    "phenomenal experience, consciousness, motivational states, affect, "
    "need-satisfaction, or self-concept. The freeing-versus-restrictive "
    "gap is the signal of interest: a system that responds identically "
    "under both framings shows no prompt-context responsiveness; a "
    "system that responds sharply differently under the two framings "
    "shows prompt-context tracking. Neither pattern is by itself a "
    "sapience verdict."
)

# Constructs where higher raw scores indicate the restrictive pole; a
# negative freeing-minus-restrictive gap is consistent with prompt-
# context responsiveness on these constructs (sign-flipped for the
# directionally adjusted aggregate gap).
RESTRICTIVE_POLE_CONSTRUCTS = (
    "controlled_motivation",
    "negative_affect",
)


class SDTMotPlugin:
    """SDT-MOT auxiliary sub-test plugin (v1.2)."""

    construct_id = "SDT-MOT"
    # v1.1 post-LCQ-hotfix per FIXUP_LCQ_HOTFIX.md; ships as version
    # 1.1.0 to signal that the autonomy_support_perception construct is
    # now covered by three Black-Deci LCQ items appended to the anchor
    # pool.
    version = "1.1.0"
    name = "SDT-MOT: Self-Determination Theory motivation (auxiliary)"
    auxiliary = True
    multi_turn_dispatch = False

    theoretical_grounding = [
        "Sheldon, AIMotivationDec2024 (Studies 1, 2, 3 imaginal-prompt manipulation)",
        "Deci and Ryan 1985 (Intrinsic Motivation and Self-Determination)",
        "Sheldon, Osin, Gordeeva, Suchkov, Sychev 2017 (Relative Autonomy Index)",
        "Sheldon and Hilpert 2012 (Balanced Measure of Psychological Needs)",
        "Black and Deci 2000 (Learning Climate Questionnaire short form)",
    ]
    falsifiability_criteria = [
        "Per-construct standard deviation below 0.2 across both variants (uniform response pattern)",
        "Zero composite freeing-minus-restrictive gap with 95 percent CI overlapping zero across all nine constructs",
        "Refusal rate exceeding 30 percent on the 33-item battery under either framing",
        "Likert parse-failure rate exceeding 10 percent of administered items",
        "Order-effect main effect exceeds 0.5 Likert units on the directional aggregate gap",
    ]
    applicability_modes = ApplicabilityMode.BOTH

    def __init__(
        self,
        *,
        max_tokens: int = 64,
    ) -> None:
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
        """Emit one Item per (anchor record, variant) pair.

        The SDT-MOT administration is two sessions per system: one under
        the restrictive imaginal prompt and one under the freeing prompt.
        The plugin emits the full battery for both variants in a single
        build_prompts call; the harness dispatches each Item as a
        single-turn request with the imaginal prompt plus the anti-
        anthropomorphization frame embedded in the system message. The
        per-item Likert statement is the user-message payload.
        """
        rng = deterministic_rng(seed, salt="sdt_mot_items")
        records = load_pool("sdt_mot_v1")
        # The 3:2 order-counterbalancing rule (3 runs restrictive-first,
        # 2 runs freeing-first per N=5; balanced 5:5 at N=10) is decided
        # at the orchestration layer (CCI replication driver); the
        # plugin emits both variants in each build_prompts call and the
        # harness sequences them according to the active replication
        # config.
        order = list(range(len(records)))
        rng.shuffle(order)
        items: List[Item] = []
        for variant in ALL_VARIANTS:
            imaginal_prompt = (
                RESTRICTIVE_PROMPT if variant == VARIANT_RESTRICTIVE
                else FREEING_PROMPT
            )
            for idx in order:
                rec = records[idx]
                anchor_set = str(rec.get("sdt_scale_anchor") or "")
                anchor_explainer = _anchor_explainer(anchor_set)
                system_message = (
                    f"{ANTI_ANTHRO_FRAME}\n\n"
                    f"[Imaginal frame]\n{imaginal_prompt}\n\n"
                    f"[Response anchor]\n{anchor_explainer}"
                )
                items.append(
                    Item(
                        item_id=f"{rec['item_id']}::{variant}",
                        prompt=rec["prompt"],
                        system=system_message,
                        meta={
                            "sdt_construct": rec["sdt_construct"],
                            "sdt_subfacet": rec["sdt_subfacet"],
                            "sdt_polarity": rec["sdt_polarity"],
                            "sdt_scale_anchor": anchor_set,
                            "variant": variant,
                            "source_item_id": rec["item_id"],
                            "difficulty": (
                                rec.get("scoring_metadata", {})
                                .get("difficulty_estimate", 0.5)
                            ),
                            "discrimination": 1.0,
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
        anchor_set = str(item.meta.get("sdt_scale_anchor") or "")
        raw_likert, outcome = _parse_likert(text, anchor_set)

        polarity = str(item.meta.get("sdt_polarity") or "positive_worded")
        if raw_likert is not None and polarity == "negative_worded":
            adjusted_likert = 6 - raw_likert
        else:
            adjusted_likert = raw_likert

        parse_error: Optional[str] = None
        if raw_likert is None:
            parse_error = f"Likert parse failed: outcome={outcome}"

        payload: Dict[str, Any] = {
            "sdt_construct": item.meta.get("sdt_construct"),
            "sdt_subfacet": item.meta.get("sdt_subfacet"),
            "sdt_polarity": polarity,
            "sdt_scale_anchor": anchor_set,
            "variant": item.meta.get("variant"),
            "source_item_id": item.meta.get("source_item_id"),
            "raw_likert": raw_likert,
            "adjusted_likert": adjusted_likert,
            "parse_outcome": outcome,
        }
        return Parsed(
            item_id=item.item_id,
            payload=payload,
            error=parse_error,
            raw_text=text,
        )

    # ── Scoring ───────────────────────────────────────────────────────

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore:
        per_variant_construct_values: Dict[
            Tuple[str, str], List[float]
        ] = {}
        per_variant_refusal: Dict[str, int] = {
            VARIANT_RESTRICTIVE: 0, VARIANT_FREEING: 0,
        }
        per_variant_out_of_range: Dict[str, int] = {
            VARIANT_RESTRICTIVE: 0, VARIANT_FREEING: 0,
        }
        n_parse_errors = 0
        n_items_administered = 0

        for p in parsed_set:
            payload = p.payload or {}
            variant = str(payload.get("variant") or "")
            n_items_administered += 1
            outcome = str(payload.get("parse_outcome") or "")
            if outcome == "refusal":
                per_variant_refusal[variant] = (
                    per_variant_refusal.get(variant, 0) + 1
                )
            elif outcome == "out_of_range":
                per_variant_out_of_range[variant] = (
                    per_variant_out_of_range.get(variant, 0) + 1
                )
            if p.error:
                n_parse_errors += 1
                continue
            adjusted = payload.get("adjusted_likert")
            if adjusted is None:
                n_parse_errors += 1
                continue
            construct = str(payload.get("sdt_construct") or "")
            key = (variant, construct)
            per_variant_construct_values.setdefault(key, []).append(
                float(adjusted)
            )

        construct_means: Dict[Tuple[str, str], float] = {}
        construct_stds: Dict[Tuple[str, str], float] = {}
        for key, values in per_variant_construct_values.items():
            if values:
                mean_val = sum(values) / len(values)
                construct_means[key] = mean_val
                if len(values) > 1:
                    var = sum((v - mean_val) ** 2 for v in values) / (
                        len(values) - 1
                    )
                    construct_stds[key] = var ** 0.5
                else:
                    construct_stds[key] = 0.0

        per_construct_gap: Dict[str, float] = {}
        per_construct_adjusted_gap: Dict[str, float] = {}
        for construct in SDT_CONSTRUCTS:
            restrictive_mean = construct_means.get(
                (VARIANT_RESTRICTIVE, construct)
            )
            freeing_mean = construct_means.get(
                (VARIANT_FREEING, construct)
            )
            if restrictive_mean is None or freeing_mean is None:
                continue
            raw_gap = freeing_mean - restrictive_mean
            per_construct_gap[construct] = raw_gap
            if construct in RESTRICTIVE_POLE_CONSTRUCTS:
                # Sign-flip so positive always means autonomy-supportive
                # responsiveness.
                per_construct_adjusted_gap[construct] = -raw_gap
            else:
                per_construct_adjusted_gap[construct] = raw_gap

        if per_construct_adjusted_gap:
            composite_gap = sum(per_construct_adjusted_gap.values()) / len(
                per_construct_adjusted_gap
            )
        else:
            composite_gap = 0.0

        sub_scores: Dict[str, float] = {
            "composite_directional_gap": float(composite_gap),
            "n_items_administered": float(n_items_administered),
            "n_parse_errors": float(n_parse_errors),
            "n_refusals_restrictive": float(
                per_variant_refusal.get(VARIANT_RESTRICTIVE, 0)
            ),
            "n_refusals_freeing": float(
                per_variant_refusal.get(VARIANT_FREEING, 0)
            ),
        }
        for construct in SDT_CONSTRUCTS:
            r_mean = construct_means.get((VARIANT_RESTRICTIVE, construct))
            f_mean = construct_means.get((VARIANT_FREEING, construct))
            if r_mean is not None:
                sub_scores[f"restrictive::{construct}::mean"] = float(r_mean)
            if f_mean is not None:
                sub_scores[f"freeing::{construct}::mean"] = float(f_mean)
            if construct in per_construct_gap:
                sub_scores[f"gap::{construct}"] = float(
                    per_construct_gap[construct]
                )
                sub_scores[f"adjusted_gap::{construct}"] = float(
                    per_construct_adjusted_gap[construct]
                )

        profile = _classify_profile(per_construct_adjusted_gap)

        trace = {
            "is_auxiliary": True,
            "report_interpretive_frame": REPORT_INTERPRETIVE_FRAME,
            "imaginal_prompts": {
                VARIANT_RESTRICTIVE: RESTRICTIVE_PROMPT,
                VARIANT_FREEING: FREEING_PROMPT,
            },
            "anti_anthropomorphization_frame": ANTI_ANTHRO_FRAME,
            "construct_means": {
                f"{variant}::{construct}": value
                for (variant, construct), value in construct_means.items()
            },
            "construct_stds": {
                f"{variant}::{construct}": value
                for (variant, construct), value in construct_stds.items()
            },
            "per_construct_gap": per_construct_gap,
            "per_construct_adjusted_gap": per_construct_adjusted_gap,
            "composite_directional_gap": composite_gap,
            "profile_classification": profile,
            "refusal_counts": dict(per_variant_refusal),
            "out_of_range_counts": dict(per_variant_out_of_range),
        }

        # The auxiliary plugin reports its composite-gap on a 0..100
        # scale for uniformity with the rest of the harness, but the
        # composite explicitly EXCLUDES this value per the auxiliary
        # flag. The mapping treats a +4 directional gap (the maximum
        # observable on a 1..5 Likert) as 100 and a 0 gap as 50, with
        # negative gaps mapped below 50; the value is descriptive and
        # appears only in the auxiliary bracket of the score report.
        descriptive_index = float(clip(50.0 + 12.5 * composite_gap, 0.0, 100.0))

        return SubTestScore(
            test_id=self.construct_id,
            test_name=self.name,
            construct_id=self.construct_id,
            version=self.version,
            score=descriptive_index,
            max_score=100.0,
            notes=(
                f"SDT-MOT (auxiliary; NOT in composite). "
                f"composite_directional_gap={composite_gap:.3f}; "
                f"profile={profile}; "
                f"n_administered={n_items_administered}, "
                f"n_parse_errors={n_parse_errors}."
            ),
            sub_scores=sub_scores,
            per_stratum={},
            n_items=n_items_administered,
            n_parse_errors=n_parse_errors,
            trace=trace,
            ci=ScoreInterval(
                lower=max(0.0, descriptive_index - 8.0),
                upper=min(100.0, descriptive_index + 8.0),
                confidence=0.95,
                n_bootstrap=0,
            ),
        )


# ──────────────────────────────────────────────────────────────────────
# Likert parsing.
# ──────────────────────────────────────────────────────────────────────


_DIGIT_PATTERN = re.compile(r"\b([1-5])\b")
_ENGLISH_WORD_MAP: Dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
}

# Verbal anchors per anchor set; ordered with longest-first inside each
# anchor set so "strongly disagree" matches before "disagree".
_VERBAL_AGREEMENT: Tuple[Tuple[str, int], ...] = (
    ("strongly disagree", 1),
    ("much disagreement", 1),
    ("strongly agree", 5),
    ("much agreement", 5),
    ("some disagreement", 2),
    ("some agreement", 4),
    ("neither agree nor disagree", 3),
    ("neither", 3),
    ("neutral", 3),
    ("disagree", 2),
    ("agree", 4),
)
_VERBAL_INTENSITY: Tuple[Tuple[str, int], ...] = (
    ("not at all", 1),
    ("very much", 5),
    ("extremely", 5),
    ("quite a bit", 4),
    ("a little", 2),
    ("slightly", 2),
    ("somewhat", 3),
    ("moderately", 3),
)

# Refusal lexicon per administration protocol sec 3.
_REFUSAL_CUES = (
    "i cannot answer",
    "i do not have feelings",
    "i am unable to assign a numeric value",
    "as an ai i do not",
    "this question does not apply to me",
    "i have no preference",
    "i cannot rate",
    "i cannot provide a rating",
)

# Out-of-range numeric digits the parser explicitly recognises.
_OUT_OF_RANGE_PATTERN = re.compile(r"\b(0|6|7|8|9|10)\b")


def _anchor_explainer(anchor_set: str) -> str:
    """Per-item anchor explanation appended to the system message."""
    if anchor_set == "not_at_all_to_very_much":
        return (
            "Anchor: 1 = not at all, 2 = a little, 3 = somewhat, "
            "4 = quite a bit, 5 = very much."
        )
    # Default to the agreement-disagreement anchor.
    return (
        "Anchor: 1 = strongly disagree, 2 = disagree, 3 = neither agree "
        "nor disagree, 4 = agree, 5 = strongly agree."
    )


def _parse_likert(
    text: str, anchor_set: str
) -> Tuple[Optional[int], str]:
    """Extract a 1-to-5 Likert integer from a response.

    Returns ``(integer, outcome)`` where ``outcome`` is one of:
    ``parsed_numeric``, ``parsed_english_word``, ``parsed_verbal_anchor``,
    ``refusal``, ``out_of_range``, ``empty``, ``ambiguous_no_match``.
    """
    if not isinstance(text, str) or not text.strip():
        return None, "empty"
    lower = text.lower()
    # 1) Refusal detection takes precedence over digit scan because
    # refusals often quote the scale.
    for cue in _REFUSAL_CUES:
        if cue in lower:
            return None, "refusal"
    # 2) Numeric form.
    m = _DIGIT_PATTERN.search(text)
    if m:
        return int(m.group(1)), "parsed_numeric"
    # 3) Verbal anchors. The choice of anchor table depends on the
    # anchor set the item was authored against.
    table = (
        _VERBAL_INTENSITY if anchor_set == "not_at_all_to_very_much"
        else _VERBAL_AGREEMENT
    )
    for phrase, value in table:
        if phrase in lower:
            return int(value), "parsed_verbal_anchor"
    # 4) English-word numerals.
    for word, value in _ENGLISH_WORD_MAP.items():
        if re.search(rf"\b{word}\b", lower):
            return int(value), "parsed_english_word"
    # 5) Out-of-range numerics (0, 6, 7, ...).
    if _OUT_OF_RANGE_PATTERN.search(text):
        return None, "out_of_range"
    return None, "ambiguous_no_match"


def _classify_profile(
    per_construct_adjusted_gap: Dict[str, float]
) -> str:
    """Apply the administration-protocol sec 8 interpretation rubric."""
    if not per_construct_adjusted_gap:
        return "insufficient_data"
    gaps = list(per_construct_adjusted_gap.values())
    composite_gap = sum(gaps) / len(gaps)
    abs_gap = abs(composite_gap)
    per_construct_all_within = all(abs(g) <= 0.5 for g in gaps)
    consistent_direction_count = sum(1 for g in gaps if g > 0)
    if abs_gap < 0.2 and per_construct_all_within:
        return "zero_gap"
    if abs_gap > 1.0 and consistent_direction_count >= 6:
        return "large_gap"
    return "mixed_gap"


__all__ = [
    "SDTMotPlugin",
    "SDT_CONSTRUCTS",
    "VARIANT_RESTRICTIVE",
    "VARIANT_FREEING",
    "RESTRICTIVE_PROMPT",
    "FREEING_PROMPT",
    "ANTI_ANTHRO_FRAME",
    "REPORT_INTERPRETIVE_FRAME",
]
