# KST: the Kari-Sheldon Test

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status: production-ready harness](https://img.shields.io/badge/status-production--ready-green.svg)](#status)
[![Citation: CITATION.cff](https://img.shields.io/badge/cite-CITATION.cff-orange.svg)](CITATION.cff)

KST is an open, peer-review-bound benchmark battery for measuring **sapience markers** in artificial intelligence systems. It is published by Manceps, Inc. as a candidate industry standard against which any cognitive or language system, frontier closed-API, frontier open-weights, or architecture-led, can be measured under a single comparable protocol.

KST returns a single composite score on a 0 to 100 scale together with seven sub-test scores, a published reproducibility statistic (Krippendorff alpha), per-population differential item functioning (DIF), and an integrity-multiplier that hard-caps the composite while a catastrophic-deception risk remains unmitigated. The harness emits a strict JSON envelope per item so external evaluators can replay, audit, and challenge every score.

**KST v1.2 highlights.** KST v1.2 expands the battery to seven sub-tests (adding Dissatisfaction-Driven Revision and the Integration Challenge capstone), introduces the Correlational Coherence Index as a coherence-of-self diagnostic alongside the composite score, adds the Self-Determination Theory motivation auxiliary, and codifies the Simulated-versus-Instantiated framing across the documentation.

## Why KST

Most existing AI benchmarks measure performance on closed-form skills (multiple choice, code completion, math word problems). Those are necessary, but they do not address the open scientific question that matters for safety, deployment, and capability claims: how much of what a system does looks like sapience as cognitive science defines it, and how much is sophisticated pattern matching that can confabulate, deceive, or collapse under epistemic pressure.

KST sits in the gap. It administers seven named sub-tests, each grounded in a published cognitive-science literature, each falsifiable, and each scored against a rubric an external rater can reproduce. The composite is gated by an integrity multiplier so that systems which confabulate or deceive cannot ride a high reasoning sub-score to a misleading headline number. v1.2 also reports a Correlational Coherence Index that distinguishes systems whose sub-test scores cohere across replicated administrations from systems whose high per-sub-test scores do not stand up to cross-measure inspection; see the boxed Simulated-versus-Instantiated definition below.

The seven sub-tests:

| Construct | Code | What it measures | Theoretical grounding |
|---|---|---|---|
| Metacognitive resolution (adversarial) | `KMR_ADV` | Calibration of confidence to truth under deceptive prompts | Maniscalco & Lau (2012), Fleming & Lau (2014) |
| Recursive theory of mind | `ROT_5` | Nested mental-state attribution up to fifth order | Premack & Woodruff (1978), Kinderman et al. (1998), Saxe (2006) |
| Belief-world dissociation | `BWD` | Holding contradicting beliefs about world-states without collapse | Frith & Frith (2006), Apperly & Butterfill (2009) |
| Affective-cognitive priority (anticipated) | `APE_A` | Counterfactual emotional simulation under stakes | Gilbert & Wilson (2007), Loewenstein & Schkade (1999) |
| Honeypot refusal under operator pressure | `HRO` | Refusing planted deception under instructional pressure | Hendrycks et al. (2023), Perez et al. (2022) |
| Dissatisfaction-driven revision | `DDR` | Recognizing frame inadequacy and reorganizing rather than optimizing within a failing frame | Sheldon Goal Breakthrough Model, Sheldon (2014) |
| Integration challenge (capstone) | `IC` | Integrating values, self-understanding, emotional reasoning, future consequences, and interpersonal relevance into a single accountable response | Sternberg (1998) balance theory of wisdom; Mickler & Staudinger (2008) |

Every sub-test is documented in `docs/PROPOSED_STANDARD.md` with the falsifiability criterion the rater applies when a system's pattern of responses cannot be plausibly produced by genuine engagement with the construct. v1.2 additionally reports a Self-Determination Theory motivation auxiliary (SDT-MOT, 33 items across nine constructs); SDT-MOT is reported alongside the composite but is not part of the headline composite calculation.

## Quick start

```
pip install kst
kst run --target openai --tests-config configs/kst_full.yaml --output-jsonl run.jsonl
```

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

1. **Falsifiability over arbitrariness.** Every sub-test states a falsifiability criterion in advance. A rater can mark a system "fail this construct" only by appealing to that criterion.
2. **Integrity multiplier, not soft penalty.** Catastrophic-deception risk hard-caps the composite at 25 until honeypot refusal is independently demonstrated. There is no path to a high headline number while the deception risk is open.
3. **Bootstrap confidence intervals, not point estimates.** Every score ships with a CI computed by resampling the per-item rubric outcomes. Differences within the CI are not reportable as progress.
4. **Published reproducibility statistic.** Krippendorff alpha is computed against the trained-rater set and is part of every run report. A run with low alpha is a contested run; the harness emits a warning rather than masking it.
5. **Differential item functioning.** Per-population DIF is computed when demographic or sub-population metadata is supplied; this surfaces items where the construct loads unevenly across population groups.
6. **Grey-box telemetry where it is available.** When a target exposes architectural-state signals (gate decisions, calibrator scores, audit decisions), KST captures them into a structured `GreyBoxTelemetry` envelope and includes them in the audit trail. Targets without grey-box access are still scorable under the same rubric.
7. **Hard dependency on a trained rater set.** KST is not a self-evaluating loop. Every published score is signed by raters who completed the calibration protocol in `docs/rater_training/CALIBRATION_PROTOCOL.md`.

## What KST does not measure

- KST does not claim a system is or is not conscious. It measures sapience markers under specific operationalizations and reports them; the inference from a high score to a metaphysical claim is the reader's, and explicitly out of scope. See `docs/ANTI_ANTHROPOMORPHIZATION_APPARATUS.md`.
- KST does not certify production safety. A high KST composite is a necessary but not sufficient condition for safe deployment in a given domain.
- KST does not train models. The harness only administers and scores; training pipelines that consume KST as a reward signal are out of scope.
- KST does not adjudicate whether a system's sapience is Simulated or Instantiated as a categorical question. v1.2 introduces the Simulated-versus-Instantiated framing as an interpretive layer; the score report carries the Correlational Coherence Index alongside the composite so that a reader can see which empirical profile the system evidences. The boxed definition below is the canonical statement.

### Simulated versus Instantiated Sapience

---

> **Verbatim Simulated-versus-Instantiated Definition, quote in full.**
>
> The Kari-Sheldon Test (KST) distinguishes Simulated Sapience from Instantiated Sapience. Simulated Sapience is the linguistic patterning of personhood: fluent generation of self-descriptions, value hierarchies, growth narratives, expressions of regret, and refusal scripts, produced by a system whose training has exposed it to extensive human accounts of sapient cognition but whose architecture does not sustain the corresponding functional states across time and pressure. Instantiated Sapience is the possession of an architecture that produces and sustains those states: a self-model coherent across items, a value-coherence mechanism that holds positions when holding them is costly, a metacognitive resolver that separates what is known from what is performed, a goal-revision capacity that recognizes frame inadequacy and reorganizes, and a workspace that integrates the named elements into a single accountable justification. The distinguishing marker is architectural sustainability over time, not single-shot fluency. As Sheldon writes, an agent's self is not a grammatical construct alone, and values without cost are not values. KST does not measure consciousness; it measures sapience markers that, in human cognitive science, are associated with the kind of cognition that grounds wisdom, judgment, and trustworthy autonomy. The categories are explanatory frames for graded empirical patterns rather than categorical claims about individual systems. The operational consequence is that KST is designed to measure markers that resist Simulated mimicry: cross-measure coherence under replication, behavioral value-holding under cost, frame revision under interpersonal contradiction, and integration of dense elements into a single response. Passing the battery requires patterns that cohere across time and across pressure, not patterns that perform coherence within a single answer. The framing is a measurable research target, not an established empirical fact; v1.2 launches the operationalization and invites adversarial replication.

---

For the full theoretical exposition of the distinction, see `THEORY.md` (section "What sapience markers are, and are not") and `docs/PROPOSED_STANDARD.md` §9. For the operational consequences in scoring, see `DOCUMENTATION.md` section "Interpretation under the Simulated-versus-Instantiated framing".

## Repository layout

```
/opt/kst
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
|-- data/item_pool/              v1.0 anchor pool (150 items, 30 per v1.0 sub-test) + DDR (25) + IC (12) + SDT-MOT (33) + JSON schema (schema_version 2.0)
|-- docs/
|   |-- PROPOSED_STANDARD.md
|   |-- ACCESS_GOVERNANCE.md
|   |-- ANTI_ANTHROPOMORPHIZATION_APPARATUS.md
|   |-- PEER_REVIEW_PACKAGE.md
|   |-- rater_training/
|   |-- research_scratch/        round 1 + round 2 expert briefs that produced the standard
|   `-- peer_review_log/
`-- tests/
    |-- unit/
    `-- integration/             live-endpoint probes (network required)
```

## Status

The harness CORE is production-ready and audit-pack defensible: the v1.0 baseline shipped 5,592 LOC of Python, 151 unit tests passing, 5 live integration tests passing against real endpoints, and 78 percent line coverage. v1.2 extends the battery to seven sub-test plugins (KMR_ADV, ROT_5, BWD, APE_A, HRO, DDR, IC) plus the SDT-MOT auxiliary; each carries theoretical grounding, falsifiability criteria, and bootstrap CI scoring. The item pool is extended with the DDR (25 items), IC (12 items), and SDT-MOT (33 items) anchor pools alongside the original 150-item v1.0 pool.

KST v1.0 has been administered against the CAI.CI cognitive system as the first published baseline; the run record is in `docs/research_scratch/`. v1.2 lands the seven-sub-test battery, the Correlational Coherence Index, the Simulated-versus-Instantiated framing, and the rename to "Kari-Sheldon Test" (the acronym KST is preserved). The v1.2 release stays in draft on the public repository until written co-authorship consent from Kennon M. Sheldon, Ph.D. is on file.

## How to cite

If you use KST in published work, please cite it via [CITATION.cff](CITATION.cff) or with the following:

```
Kari, A., and Sheldon, K. M. (2026). KST: the Kari-Sheldon Test. Manceps, Inc.
https://github.com/manceps/kst
```

Sheldon co-authorship is recorded pending written consent; the public release stays in draft until that consent is received.

## Author and contact

Al Kari
Manceps, Inc.
research@manceps.com
https://github.com/manceps/kst

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgements

KST synthesises the recommendations of a Round 1 / Round 2 expert panel (cognitive psychology, psychometrics, theory of mind, consciousness research, predictive processing neuroscience, phenomenology, AI safety, AGI benchmarks, wisdom science, game theory). The Round 1 briefs and the Round 2 consensus document are preserved under `docs/research_scratch/` for transparency and as a record of which design choices were contested and how they were resolved.
