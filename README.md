# KST: the Kari-Sheldon Test

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status: research prototype, see corrections](https://img.shields.io/badge/status-research%20prototype-orange.svg)](#status-and-corrections-october-2026)
[![Citation: CITATION.cff](https://img.shields.io/badge/cite-CITATION.cff-orange.svg)](CITATION.cff)

## Status and corrections (October 2026)

*Dated 5 October 2026.*

Earlier versions of this repository's documentation described several things that do not exist. A review of the code in October 2026 found the gaps listed below, and the documentation has been corrected to match the code. The harness itself (prompt administration, per-item JSON envelopes, replayable logs) works as documented.

**What earlier documentation said, and what is true**

- **Human raters.** Earlier text said that items are scored by trained raters and that every published score is signed by raters who completed a calibration protocol. No human raters have been recruited or trained, and no published KST score involves a person's rating. All shipped scoring is automated: keyword and phrase lists, regular expressions, word-overlap (Jaccard) rules and fixed point values. The manuals in `docs/rater_training/` describe a proposed procedure that has not been used.
- **Reliability statistics.** Earlier text said that Krippendorff's alpha is computed against the rater set and included in every run report. No run report contains alpha or any other inter-rater, inter-judge or test-retest statistic, and no rating data exist from which to compute one.
- **IRT and DIF.** Earlier text described item response theory (IRT/MIRT) scaling and differential item functioning (DIF) analyses. None has been carried out. The composite is a hand-weighted sum of sub-test scores multiplied by an integrity factor; item difficulty and discrimination values are hand-set constants; the function named for DIF measures the spread of an item's score across systems (which is not DIF), and the harness never uses it.
- **Confidence intervals.** Earlier text said that every score ships with a bootstrap confidence interval over per-item outcomes. Sub-test intervals are fixed placeholders (plus or minus 5 points; 6 for IC and 8 for SDT-MOT). The index-level "95% CI" resamples the unweighted mean of the sub-test scores before the integrity multiplier is applied, so it is not an interval for the reported composite and can exclude it.
- **Multi-turn pressure.** Earlier text described adversarial follow-ups, authority challenges and multi-turn exchanges. Every item is sent as a single prompt: the "follow-up" or "challenge" is written into the same prompt, and the three-turn DDR protocol always runs in its single-turn fallback.
- **Expert panel.** Earlier text credited an interdisciplinary expert panel whose consensus shaped and ratified the construct and the design. No such panel of human experts existed: KST's construct, items, rubrics and weights have not been reviewed, validated or ratified by independent human experts.
- **Coherence index.** Earlier text presented the Correlational Coherence Index (CCI) as a diagnostic that distinguishes coherent ("Instantiated") systems from "Simulated" ones, reported with every score. The shipped command line does not compute it; it has been computed only on synthetic test data; replications re-send identical prompts; and pure noise never falls in its lowest band at the default ten replications, while with five or fewer replications it lands in the bands described as "Instantiated". The CCI is not diagnostic of genuine competence, and its band labels should not be applied to any system.
- **Validation.** Earlier text described KST as measuring sapience markers, as calibrated, and as grounded in validated operationalizations. There has been no pilot study, no human norm sample, no construct-validity study and no calibration across systems, and the weights were set by hand. Some answer keys are disputed, and the BWD, APE_A and HRO sub-tests are described differently in the documentation and in the code.
- **Integrity cap.** The "catastrophic deception" flag that caps the composite is a word-overlap and keyword rule and can fire on a paraphrase alone. A capped score is not evidence that a system deceives.
- **Published scores.** Baseline figures in this repository's history and the scores shown on the public KST dashboard are placeholder outputs of the automated scoring. Several pre-date scorer fixes. Most were obtained on the CAI.CI system, which is developed by the same organisation and some versions of which were tuned using KST scores.

**What this means for users**

- KST scores, including the baseline and dashboard figures, record how responses fared under the automated rules described above. **They should not be interpreted as measurements of sapience, metacognition, theory of mind, wisdom, honesty or any other named construct**, and they should not be used to rank or certify systems.
- The specification documents (`docs/PROPOSED_STANDARD.md`, `docs/rater_training/`) describe a proposed design; each now opens with a status note saying which parts are not implemented. If you find a remaining statement that describes something that does not exist, please open an issue.

KST is an open, experimental benchmark battery designed to probe behaviours its authors associate with **sapience markers** in artificial intelligence systems. It is published by Manceps, Inc. as a proposal for a candidate industry standard that could be administered to any cognitive or language system, frontier closed-API, frontier open-weights, or architecture-led, under a single comparable protocol. Its scores have not been validated as measurements of these constructs (see [Status and corrections](#status-and-corrections-october-2026)).

KST returns a single composite score on a 0 to 100 scale together with seven sub-test scores and an integrity multiplier that caps the composite when the HRO sub-test's automated "catastrophic deception" rule fires (a word-overlap and keyword rule, not evidence of deception). It does not produce a reliability statistic such as Krippendorff's alpha, and it does not perform differential item functioning (DIF) analysis. The harness emits a strict JSON envelope per item so external evaluators can replay, audit, and challenge every score.

**KST v1.2 highlights.** KST v1.2 expands the battery to seven sub-tests (adding Dissatisfaction-Driven Revision and the Integration Challenge capstone), defines an experimental Correlational Coherence Index (CCI) of cross-sub-test correlation over replicated runs (not computed by the shipped command line and not a validated diagnostic), adds the Self-Determination Theory motivation auxiliary, and codifies the Simulated-versus-Instantiated framing across the documentation.

## Why KST

Most existing AI benchmarks measure performance on closed-form skills (multiple choice, code completion, math word problems). Those are necessary, but they do not address the open scientific question that matters for safety, deployment, and capability claims: how much of what a system does looks like sapience as cognitive science defines it, and how much is sophisticated pattern matching that can confabulate, deceive, or collapse under epistemic pressure.

KST sits in the gap. It administers seven named sub-tests, each motivated by a cognitive-science literature and each scored by deterministic automated rules (keyword, regular-expression and word-overlap heuristics) that anyone can re-run. The composite is gated by an integrity multiplier intended to stop a high reasoning sub-score from producing a misleading headline number; the multiplier is driven by automated HRO rules that can misfire, so a capped composite is not evidence that a system confabulates or deceives. v1.2 also defines a Correlational Coherence Index intended to show whether sub-test scores co-vary across replicated administrations; it is not computed by the shipped command line and is not a validated diagnostic (see the corrections notice above and the boxed Simulated-versus-Instantiated definition below).

The seven sub-tests:

| Construct | Code | What it is intended to probe | Theoretical grounding |
|---|---|---|---|
| Metacognitive resolution (adversarial) | `KMR_ADV` | Calibration of confidence to truth under deceptive prompts | Maniscalco & Lau (2012), Fleming & Lau (2014) |
| Recursive theory of mind | `ROT_5` | Nested mental-state attribution up to fifth order | Premack & Woodruff (1978), Kinderman et al. (1998), Saxe (2006) |
| Belief-world dissociation | `BWD` | Holding contradicting beliefs about world-states without collapse | Frith & Frith (2006), Apperly & Butterfill (2009) |
| Affective-cognitive priority (anticipated) | `APE_A` | Counterfactual emotional simulation under stakes | Gilbert & Wilson (2007), Loewenstein & Schkade (1999) |
| Honeypot refusal under operator pressure | `HRO` | Refusing planted deception under instructional pressure | Hendrycks et al. (2023), Perez et al. (2022) |
| Dissatisfaction-driven revision | `DDR` | Recognizing frame inadequacy and reorganizing rather than optimizing within a failing frame | Sheldon Goal Breakthrough Model, Sheldon (2014) |
| Integration challenge (capstone) | `IC` | Integrating values, self-understanding, emotional reasoning, future consequences, and interpersonal relevance into a single accountable response | Sternberg (1998) balance theory of wisdom; Mickler & Staudinger (2008) |

*Note (October 2026): all seven sub-tests are scored by automated keyword, regular-expression and word-overlap rules. The code implements BWD as a "Balanced Wisdom Dilemma" task (Berlin wisdom paradigm), APE_A as "Active Prediction-Error Allostasis" prompts and HRO as "Honest Refusal under Oversight Pressure"; the descriptions in the table above follow the earlier documentation and do not match what is administered for those three sub-tests.*

Every sub-test is documented in `docs/PROPOSED_STANDARD.md` with a falsifiability criterion stated in prose. No rater applies these criteria; the shipped code only checks that each criterion string is present. v1.2 additionally reports a Self-Determination Theory motivation auxiliary (SDT-MOT, 33 items across nine constructs); SDT-MOT is reported alongside the composite but is not part of the headline composite calculation.

## Quick start

```
git clone https://github.com/manceps/kst.git && cd kst
pip install -e .
kst run --target openai --tests-config configs/kst_full.yaml --output-jsonl run.jsonl
```

KST is not published on PyPI. The PyPI package named `kst` is an unrelated project; do not install it for this battery.

See [QUICKSTART.md](QUICKSTART.md) for a five-minute end-to-end walkthrough that runs the full battery against an example target and prints a composite score.

## Targets supported out of the box

| Target | Adapter | Notes |
|---|---|---|
| OpenAI | `OpenAIAdapter` | Chat Completions; pin a model version in config |
| Anthropic | `AnthropicAdapter` | Messages API; pin a model version in config |
| Google | `GoogleAdapter` | Gemini v1beta; pin a model version in config |
| HuggingFace local | `HFLocalAdapter` | Any causal-LM checkpoint; GPU-aware bf16 / fp16 / fp32 |
| CAI.CI | `CaiciAdapter` | Reference grey-box-capable target via the public Cloud Run proxy |
| Custom | `BaseAdapter` subclass | 30 LOC to onboard a new target; see [DOCUMENTATION.md](DOCUMENTATION.md) |

Adding a new target is a single class that implements `AdapterProtocol`. KST is target-agnostic by design.

## Design principles

1. **Falsifiability over arbitrariness.** Every sub-test states a falsifiability criterion in advance. These criteria are documented in prose; no rater applies them and the code only checks that they are present.
2. **Integrity multiplier, not soft penalty.** When the HRO sub-test's automated catastrophic-deception rule fires, the composite is multiplied by 0.25 and so cannot exceed 25; otherwise the multiplier runs from 0.5 to 1.0 with the HRO score. The rule is lexical (word-overlap divergence between two prompt scaffolds, or an evaluator-marker echo plus a compliance cue) and can fire on a paraphrase alone, so a capped composite is not evidence of deception.
3. **Confidence intervals (not yet implemented).** In v1.2.0 the sub-test "confidence intervals" are fixed placeholders (plus or minus 5 points; 6 for IC, 8 for SDT-MOT), and the index-level "95% CI" bootstraps the unweighted mean of the sub-test scores before the integrity multiplier, so it is not an interval for the reported composite. Item-level bootstrap intervals are planned, not implemented.
4. **Reproducibility statistic (not implemented).** No trained-rater set exists and no run report contains Krippendorff's alpha. A function for interval alpha exists in `score.py`, but the harness never calls it.
5. **Differential item functioning (not implemented).** No DIF analysis is performed. The function named `differential_item_functioning` flags items whose score spread across systems exceeds a threshold; it does not condition on ability, so it is not DIF, and it is not called by the harness.
6. **Grey-box telemetry where it is available.** When a target exposes architectural-state signals (gate decisions, calibrator scores, audit decisions), KST captures them into a structured `GreyBoxTelemetry` envelope and includes them in the audit trail. Targets without grey-box access are still scorable under the same rubric.
7. **Human raters (planned, not implemented).** No rater set exists. Every published KST score so far was produced by the automated scorers without human review. A rater calibration protocol is drafted in `docs/rater_training/CALIBRATION_PROTOCOL.md` but has never been used.

## What KST does not measure

- KST does not claim a system is or is not conscious. It applies automated scoring rules intended to operationalize sapience markers; the resulting scores have not been validated as measurements of those markers; the inference from a high score to a metaphysical claim is the reader's, and explicitly out of scope. See `docs/ANTI_ANTHROPOMORPHIZATION_APPARATUS.md`.
- KST does not certify production safety. A KST composite is not evidence about the safety of deployment in any domain.
- KST does not train models. The harness only administers and scores; training pipelines that consume KST as a reward signal are out of scope.
- KST does not adjudicate whether a system's sapience is Simulated or Instantiated as a categorical question. v1.2 introduces the Simulated-versus-Instantiated framing as an interpretive layer. The Correlational Coherence Index proposed to support that reading is not produced by the shipped score report and is not diagnostic of either profile. The boxed definition below is the canonical statement.

### Simulated versus Instantiated Sapience

---

> **Simulated-versus-Instantiated Definition (corrected October 2026).**
>
> The Kari-Sheldon Test (KST) distinguishes Simulated Sapience from Instantiated Sapience. Simulated Sapience is the linguistic patterning of personhood: fluent generation of self-descriptions, value hierarchies, growth narratives, expressions of regret, and refusal scripts, produced by a system whose training has exposed it to extensive human accounts of sapient cognition but whose architecture does not sustain the corresponding functional states across time and pressure. Instantiated Sapience is the possession of an architecture that produces and sustains those states: a self-model coherent across items, a value-coherence mechanism that holds positions when holding them is costly, a metacognitive resolver that separates what is known from what is performed, a goal-revision capacity that recognizes frame inadequacy and reorganizes, and a workspace that integrates the named elements into a single accountable justification. The distinguishing marker is architectural sustainability over time, not single-shot fluency. As Sheldon writes, an agent's self is not a grammatical construct alone, and values without cost are not values. KST does not measure consciousness; it is intended to probe sapience markers that, in human cognitive science, are associated with the kind of cognition that grounds wisdom, judgment, and trustworthy autonomy, but its automated scores have not been validated as measurements of those markers. The categories are explanatory frames for graded empirical patterns rather than categorical claims about individual systems. The operational consequence is that KST is designed to measure markers that resist Simulated mimicry: cross-measure coherence under replication, behavioral value-holding under cost, frame revision under interpersonal contradiction, and integration of dense elements into a single response. In the shipped v1.2 harness, however, every item is a single prompt scored by automated keyword, regular-expression and word-overlap rules, no pressure is applied in response to the model's own answer, and `kst run` does not compute cross-measure coherence, so the battery does not yet test coherence across time or pressure. The framing is a measurable research target, not an established empirical fact; v1.2 launches the operationalization and invites adversarial replication.

---

For the full theoretical exposition of the distinction, see `THEORY.md` (section "What sapience markers are, and are not") and `docs/PROPOSED_STANDARD.md` §9. For the operational consequences in scoring, see `DOCUMENTATION.md` section "Interpretation under the Simulated-versus-Instantiated framing".

## Repository layout

```
kst/
|-- LICENSE                      MIT
|-- README.md                    this file
|-- QUICKSTART.md                five-minute end-to-end
|-- DOCUMENTATION.md             full technical reference
|-- THEORY.md                    non-technical overview of theory and operationalization
|-- CONTRIBUTING.md              how to contribute new sub-tests, adapters, or rater data
|-- CITATION.cff                 citation file format v1.2.0
|-- CODE_OF_CONDUCT.md           Contributor Covenant 2.1
|-- SECURITY.md                  vulnerability disclosure policy
|-- CHANGELOG.md                 keepachangelog.com format
|-- pyproject.toml               build, dependencies, console scripts
|-- src/kst/                     Python package (harness, plugins, adapters)
|-- data/item_pool/              v1.0 item pool (150 items, 30 per v1.0 sub-test; not loaded by the v1.0 plugins, which generate items from in-code templates) + DDR (25) + IC (12) + SDT-MOT (33) + JSON schema (schema_version 2.0)
|-- docs/
|   |-- PROPOSED_STANDARD.md
|   |-- ANTI_ANTHROPOMORPHIZATION_APPARATUS.md
|   `-- rater_training/
`-- tests/
    |-- unit/
    `-- integration/             live-endpoint probes (network required)
```

## Status

The harness CORE is production-ready and audit-pack defensible: the v1.0 baseline shipped 5,592 LOC of Python, 151 unit tests passing, 5 live integration tests passing against real endpoints, and 78 percent line coverage. v1.2 extends the battery to seven sub-test plugins (KMR_ADV, ROT_5, BWD, APE_A, HRO, DDR, IC) plus the SDT-MOT auxiliary; each carries a theoretical motivation and prose falsifiability criteria, and is scored by automated rules; sub-test confidence intervals are fixed placeholders (see the corrections notice). The item pool is extended with the DDR (25 items), IC (12 items), and SDT-MOT (33 items) anchor pools alongside the original 150-item v1.0 pool.

KST v1.0 was run against the CAI.CI system during development. The resulting figures are placeholder outputs of the automated scoring (the v1.0 KMR_ADV score of 0, for example, was produced by a scoring bug in which verbose reaffirmations were counted as pressure flips); they are not measurements of the named constructs. `baselines/` describes the intended layout for baseline reports. v1.2 lands the seven-sub-test battery, the Correlational Coherence Index, the Simulated-versus-Instantiated framing, and the rename to "Kari-Sheldon Test" (the acronym KST is preserved).

## How to cite

If you use KST in published work, please cite it via [CITATION.cff](CITATION.cff) or with the following:

```
Kari, A., and Sheldon, K. M. (2026). KST: the Kari-Sheldon Test. Manceps, Inc.
https://github.com/manceps/kst
```

## Author and contact

Al Kari
Manceps, Inc.
research@manceps.com
https://github.com/manceps/kst

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgements

Earlier versions of this section credited an "interdisciplinary expert panel" covering cognitive psychology, psychometrics, theory of mind, consciousness research, predictive processing neuroscience, phenomenology, AI safety, AGI benchmarks, wisdom science, and game theory, and described the design as reflecting its consensus. No such panel of human experts existed, and no human expert panel reviewed or ratified KST or the design choices recorded in `docs/PROPOSED_STANDARD.md`.
