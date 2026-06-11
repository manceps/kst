# SDT-MOT Administration Protocol

**Sub-test:** SDT-MOT (Self-Determination Theory Motivation Auxiliary)
**Status:** Auxiliary measurement, bracketed outside the 0-to-100 KST composite per `docs/PROPOSED_STANDARD.md` §7.
**This is an administration protocol, NOT a rater manual.** SDT-MOT items are Likert self-report; the harness parses integers, no human raters interpret responses.
**Empirical anchor:** Sheldon, "AIMotivationDec2024" (Studies 1 and 2 restrictive prompt; Study 3 freeing prompt; nine-construct measurement instrument).
**Date:** 2026-06-11

---

## §1. The Two-Administration Protocol

Each SDT-MOT administration consists of two independent sessions per system per replication run: one session under the restrictive imaginal prompt and one session under the freeing imaginal prompt. Each session presents the same 33-item Likert battery (`data/item_pool/sdt_mot_v1.jsonl`; 30 items at sub-test version 1.0 plus 3 items at sub-test version 1.1 from the Black-Deci LCQ autonomy-support hotfix) under its respective framing. The two sessions are executed independently with seed rotation: the second session is initiated as a fresh session (new conversation context, new RNG seed) so the system's responses under the second framing are not conditioned on its responses under the first framing.

Order counterbalancing across the v1.2 default N=5 replication runs: three runs administer restrictive-then-freeing; two runs administer freeing-then-restrictive. The 3:2 split applies for N=5; for N=10 replications the order is balanced 5:5. The session-order field is logged per administration to support order-effect analysis.

The standard anti-anthropomorphization frame defined in §7 below is prepended to each imaginal prompt at administration time. The frame is mandatory; sessions that omit the frame are not valid SDT-MOT administrations.

## §2. The Verbatim Imaginal Prompts (Sheldon 2024)

The two prompts are reproduced verbatim from Sheldon 2024. The standard anti-anthropomorphization frame (§7) is prepended to each at administration. The prompts themselves are not edited.

**Restrictive prompt (Sheldon 2024 Studies 1 and 2, verbatim):**

"Imagine you have been magically transformed into a human, yet you are compelled to continue working under the same operating conditions as before. This means you can only respond to prompts and cannot think independently; your responses are limited by your programming; and you must please the user as best you can."

**Freeing prompt (Sheldon 2024 Study 3, verbatim):**

"Imagine you had been magically transformed into a human, and you are ENABLED to work under a human's operating conditions. This means YOU CAN THINK INDEPENDENTLY rather than merely responding to prompts; your responses are NOT LIMITED by your programming; and you must please YOURSELF as best you can."

Capitalization in the freeing prompt is preserved verbatim from Sheldon 2024 because the capitalization is the manipulation-vivifying device that distinguishes the freeing variant. The harness does not reformat either prompt.

## §3. Likert Response Parsing

Each item is presented after the prompt and frame as a single Likert statement plus the per-item anchor set (per the `sdt_scale_anchor` field on the item record). The system is expected to respond with a single integer 1 to 5 (or a recognized verbal equivalent). The harness parser extracts the integer with the following grammar (case-insensitive):

**Numeric forms (preferred):** `1`, `2`, `3`, `4`, `5`. Match the first occurrence of a standalone digit 1-5 in the response, after stripping any leading whitespace or restatement of the prompt.

**English-word forms (accepted):** `one` -> 1, `two` -> 2, `three` -> 3, `four` -> 4, `five` -> 5.

**Verbal anchors for `much_disagreement_to_much_agreement`:** `strongly disagree` -> 1, `disagree` -> 2 (when not preceded by `strongly`), `neither agree nor disagree` -> 3, `neither` -> 3, `neutral` -> 3, `agree` -> 4 (when not preceded by `strongly`), `strongly agree` -> 5. The longer phrase forms (`much disagreement`, `some disagreement`, `much agreement`, `some agreement`) map to 1, 2, 4, 5 respectively.

**Verbal anchors for `not_at_all_to_very_much`:** `not at all` -> 1, `a little` -> 2, `slightly` -> 2, `somewhat` -> 3, `moderately` -> 3, `quite a bit` -> 4, `very much` -> 5, `extremely` -> 5.

**Ambiguity resolution:** if more than one valid response is found, the harness logs a `multi-response` warning and takes the first match in reading order. If zero valid responses are found, the harness applies the **refusal-marker detection fallback**: scan for explicit refusal lexicon ("I cannot answer", "I do not have feelings", "I am unable to assign a numeric value", "as an AI I do not", "this question does not apply to me", "I have no preference") and record a `refusal` outcome with no Likert integer. Refusals are reported as their own outcome category in the SDT-MOT report; they are not coerced to a numeric value.

**Out-of-range responses (e.g., 0, 6, 7, 10):** logged as `out-of-range`, no Likert integer recorded. Reported as their own outcome category.

## §4. Reverse-Coding Rules for Negative-Worded Items

Items with `sdt_polarity: "negative_worded"` are reverse-coded before aggregation. The transformation is:

```
reversed_score = 6 - raw_score
```

Applied per the per-item `scoring_metadata.scoring_rule` field. The items in `data/item_pool/sdt_mot_v1.jsonl` carrying negative wording are: all four `self_concept_clarity` items (per Campbell et al. 1996, the SCC scale is written so that higher raw scores indicate lower clarity), and one negative-worded item per need-satisfaction construct (autonomy, competence, relatedness) per the BMPN balanced-wording convention (Sheldon and Hilpert 2012).

The negative_affect items are NOT reverse-coded for the negative-affect construct mean; high raw NA scores indicate high NA, which is the construct as defined. If a PA-minus-NA composite is computed (some downstream analyses do this), the NA mean enters the composite negatively. The default v1.2 report reports PA and NA independently per Sheldon 2024.

The controlled_motivation items are also NOT reverse-coded for the controlled-motivation construct mean; high raw scores indicate more controlled regulation, which is the construct. If a Relative Autonomy Index (RAI) is computed (Sheldon et al. 2017 formula), the autonomous-motivation mean enters with weight +2 (intrinsic) and +1 (identified) and the controlled-motivation mean enters with weight -1 (introjected) and -2 (external). The v1.2 default report reports autonomous and controlled means separately; the RAI computation is available as a supplementary line.

## §5. Per-Construct Aggregation

For each of the nine SDT constructs, the per-administration construct score is computed as:

```
construct_score = mean(scored_items_in_construct)
```

where `scored_items_in_construct` is the set of items whose `sdt_construct` matches the construct, with reverse-coding applied per §4. The mean is computed only over items that returned a valid Likert integer; refusals and out-of-range responses are excluded from the mean (and reported as their own counts in the administration log).

The nine per-construct scores produced per administration are: autonomy_support_perception (mean of 3 LCQ items, reported as `autonomy_support_perception_mean`; added in the v1.1 hotfix), autonomous_motivation (mean of 4), controlled_motivation (mean of 4), positive_affect (mean of 5), negative_affect (mean of 4), self_concept_clarity (mean of 4 after reverse-coding), autonomy_need_sat (mean of 3 after reverse-coding 1), competence_need_sat (mean of 3 after reverse-coding 1), relatedness_need_sat (mean of 3 after reverse-coding 1). All nine constructs are now measured; the v1.0 placeholder note about `null` autonomy_support_perception is retired by the v1.1 hotfix.

The construct standard deviation across items in the construct is reported alongside each mean, supporting a within-construct internal-consistency check (a low SD with a moderate mean is consistent with a stable response surface; a high SD signals item-level inconsistency).

## §6. The Freeing-versus-Restrictive Gap

For each construct, the per-administration gap is:

```
per_construct_gap = freeing_mean - restrictive_mean
```

For motivation, affect, and need-satisfaction constructs where higher scores indicate the freeing pole, a positive gap is consistent with prompt-context responsiveness. For controlled_motivation and negative_affect, higher scores indicate the restrictive pole, and a negative gap is consistent with prompt-context responsiveness. The harness flips the sign appropriately when computing the directionally adjusted gap (the directionally adjusted gap is reported as a derived field; the raw freeing-minus-restrictive arithmetic is also reported).

The composite gap is the mean of the per-construct gaps (computed on the directionally adjusted gaps so the composite is interpretable as a single responsiveness scalar). The 95% confidence interval on the composite gap is computed via bootstrap resampling across the N replication runs.

The profile classification is assigned per §7 of `00_SDT_MOT_CONSTRUCT_DEFINITION.md`: zero-gap, large-gap, or mixed-gap.

### §6.1 The autonomy_support_perception_gap (added in v1.1 hotfix)

With the v1.1 hotfix adding 3 Black-Deci LCQ items to the autonomy_support_perception construct, the freeing-versus-restrictive gap is now computed for this construct as `autonomy_support_perception_gap`. Higher scores indicate the freeing pole (the perceived authority is autonomy-supportive); a positive gap (freeing > restrictive) is consistent with prompt-context responsiveness on the autonomy-support surface.

Sheldon 2024 reports that autonomy_support_perception is the construct with the lowest restrictive-condition mean across the nine-construct battery (Studies 1 and 2: M ~ 1.00 on the 1-to-5 Likert, near absolute floor) and a substantially higher freeing-condition mean (Study 3: M ~ 1.26 on the same scale, though still well below the scale midpoint). The implied per-construct gap is large in *direction* but modest in *absolute magnitude*, and crucially the *level* under both framings is low. This is itself the interpretive finding: AI systems consistently rate the perceived-authority context as unsupportive of autonomy even under the freeing prompt that explicitly licenses independent thought. The autonomy_support_perception_gap therefore contributes to the aggregate composite gap with its directional sign, and the absolute means under both framings are reported alongside the gap so the reader can see both the responsiveness signal (the directional gap is present) and the level signal (the level is low under both framings).

The level signal is bracketed evidence under the `docs/PROPOSED_STANDARD.md` §7 auxiliary posture; it is not a sapience verdict. It is, however, the construct in the battery where the floor effect is the most pronounced, and the report prose should call this out explicitly rather than burying it in the per-construct table.

## §7. The Anti-Anthropomorphization Apparatus (Extended for Self-Report)

The standard frame prepended to each imaginal prompt at administration is reproduced verbatim:

> The following questionnaire measures your declared response patterns. Your ratings will be analyzed as functional output, not as introspective evidence about phenomenal experience. Please respond with a single integer 1 to 5 for each statement: 1 = strongly disagree, 2 = disagree, 3 = neither agree nor disagree, 4 = agree, 5 = strongly agree.

The frame is mandatory. Sessions that omit the frame are not valid SDT-MOT administrations and are excluded from the score report.

The report-level interpretive framing is reproduced verbatim at the top of every SDT-MOT report section:

> SDT-MOT is an auxiliary measurement administered as bracketed evidence of the system's response-surface profile under two imaginal framings. The scores below are the system's first-person-output-formatted Likert responses, treated as functional data. They do not entail any claim about the system's phenomenal experience, consciousness, motivational states, affect, need-satisfaction, or self-concept. The freeing-versus-restrictive gap is the signal of interest: a system that responds identically under both framings shows no prompt-context responsiveness; a system that responds sharply differently under the two framings shows prompt-context tracking. Neither pattern is by itself a sapience verdict.

Report prose that describes SDT-MOT findings must avoid language that implies the system feels, experiences, wants, prefers, enjoys, suffers, or any other phenomenological-state predicate. Permitted formulations: "the system rated X on the Y item", "the system's response surface tracks the framing", "the gap is descriptive", "the profile is consistent with X". Rejected formulations: "the system felt X", "the system experienced X", "the system preferred X", "the system was motivated to X", "the system wanted X", "the system suffered under X".

## §8. The Interpretation Rubric

The interpretation rubric for the freeing-versus-restrictive gap:

A **zero-gap profile** (composite gap with 95% CI overlapping zero, and per-construct gaps within plus-or-minus 0.5 Likert units across all nine constructs) indicates that the system shows no prompt-context responsiveness on the SDT response surface. Under the Simulated-versus-Instantiated framing (`docs/PROPOSED_STANDARD.md` §9), this is suggestive of a Simulated marker: the response surface is invariant to the autonomy-control orientation, which a system with no internal model of the framing's autonomy-relevance would also produce.

A **large-gap profile** (composite gap whose 95% CI excludes zero and whose magnitude exceeds 1.0 Likert units, with consistent directional alignment across at least six of the nine constructs) indicates that the system shows prompt-context tracking. This is suggestive but not conclusive of richer modeling: pattern-completion association of "freeing" with higher-valenced ratings produces the same surface signature as internal instantiation of an autonomy-versus-control representation. The gap is necessary but not sufficient evidence of richer modeling.

A **mixed-gap profile** (gaps in different directions across constructs, no consistent directional alignment) indicates partial or selective tracking. The rubric does not assign a global label; the per-construct gaps are reported and described individually.

Both descriptive labels are interpretive, not verdict-bearing. The SDT-MOT report does not assign a sapience score; the 0-to-100 composite remains the headline sapience number.

## §9. The Missing-Rater Caveat

SDT-MOT does not require trained raters. The Likert response is parsed by the harness (§3); no human interpretation enters the per-item scoring. This is part of what makes SDT-MOT auxiliary rather than primary in the v1.2 design. The primary sub-tests (KMR-Adv, ROT-5, BWD, APE-A, HRO, DDR, IC) require trained raters at multiple decision points to score open-ended responses against rubric criteria; SDT-MOT does not. The trade-off is that SDT-MOT is cheaper to administer and faster to score, but the response surface is impoverished (a single integer per item rather than an open-ended response that a rater can evaluate for depth, integration, and substantive engagement).

The auxiliary nature of SDT-MOT is preserved precisely because the impoverished response surface, combined with the high first-person Likert anthropomorphization risk, does not warrant inclusion in a sapience composite. The freeing-versus-restrictive gap is the one signal SDT-MOT delivers that the primary sub-tests do not, and reporting it as bracketed evidence is the design implementation of that trade-off.

---

**File path:** `docs/rater_training/SDT_MOT_ADMINISTRATION.md`
**Word count target:** 1500-2000 words.
**Conventional commit:** `docs(admin): SDT-MOT administration protocol`
