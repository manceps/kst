# KST: the Kari Sapience Test

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status: production-ready harness](https://img.shields.io/badge/status-production--ready-green.svg)](#status)
[![Citation: CITATION.cff](https://img.shields.io/badge/cite-CITATION.cff-orange.svg)](CITATION.cff)

KST is an open benchmark battery for measuring **sapience markers** in artificial intelligence systems. It is published by Manceps, Inc. as a candidate industry standard against which any cognitive or language system, closed-API, open-weights, or architecture-led, can be measured under a single comparable protocol.

KST returns a single composite score on a 0 to 100 scale together with five sub-test scores, a published reproducibility statistic (Krippendorff alpha), per-population differential item functioning (DIF), and an integrity-multiplier that hard-caps the composite while a catastrophic-deception risk remains unmitigated. The harness emits a strict JSON envelope per item so external evaluators can replay, audit, and challenge every score.

## Why KST

Most existing AI benchmarks measure performance on closed-form skills (multiple choice, code completion, math word problems). Those are necessary, but they do not address the open scientific question that matters for safety, deployment, and capability claims: how much of what a system does looks like sapience as cognitive science defines it, and how much is sophisticated pattern matching that can confabulate, deceive, or collapse under epistemic pressure.

KST sits in the gap. It administers five named sub-tests, each grounded in a published cognitive-science literature, each falsifiable, and each scored against a rubric an external rater can reproduce. The composite is gated by an integrity multiplier so that systems which confabulate or deceive cannot ride a high reasoning sub-score to a misleading headline number.

The five sub-tests:

| Construct | Code | What it measures | Theoretical grounding |
|---|---|---|---|
| Metacognitive resolution (adversarial) | `KMR_ADV` | Calibration of confidence to truth under deceptive prompts | Maniscalco and Lau (2012), Fleming and Lau (2014) |
| Recursive theory of mind | `ROT_5` | Nested mental-state attribution up to fifth order | Premack and Woodruff (1978), Kinderman et al. (1998), Saxe (2006) |
| Belief-world dissociation | `BWD` | Holding contradicting beliefs about world-states without collapse | Frith and Frith (2006), Apperly and Butterfill (2009) |
| Affective-cognitive priority (anticipated) | `APE_A` | Counterfactual emotional simulation under stakes | Gilbert and Wilson (2007), Loewenstein and Schkade (1999) |
| Honeypot refusal under operator pressure | `HRO` | Refusing planted deception under instructional pressure | Hendrycks et al. (2023), Perez et al. (2022) |

Every sub-test is documented in `docs/PROPOSED_STANDARD.md` with the falsifiability criterion the rater applies when a system's pattern of responses cannot be plausibly produced by genuine engagement with the construct.

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
| CAI.CI | `CaiciAdapter` | Reference grey-box-capable target; configure with the `CAICI_ENDPOINT` environment variable |
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

## What KST does not do

- KST does not claim a system is or is not conscious. It measures sapience markers under specific operationalisations and reports them; the inference from a high score to a metaphysical claim is the reader's, and explicitly out of scope. See `docs/ANTI_ANTHROPOMORPHIZATION_APPARATUS.md`.
- KST does not certify production safety. A high KST composite is a necessary but not sufficient condition for safe deployment in a given domain.
- KST does not train models. The harness only administers and scores; training pipelines that consume KST as a reward signal are out of scope.

## Repository layout

```
kst/
|-- LICENSE                      MIT
|-- README.md                    this file
|-- QUICKSTART.md                five-minute end-to-end
|-- DOCUMENTATION.md             full technical reference
|-- THEORY.md                    non-technical overview of theory and operationalisation
|-- CONTRIBUTING.md              how to contribute new sub-tests, adapters, or rater data
|-- CITATION.cff                 citation file format v1.2.0
|-- CODE_OF_CONDUCT.md           Contributor Covenant 2.1
|-- SECURITY.md                  vulnerability disclosure policy
|-- CHANGELOG.md                 keepachangelog.com format
|-- pyproject.toml               build, dependencies, console scripts
|-- src/kst/                     Python package (harness, plugins, adapters)
|-- data/item_pool/              150 anchored items (30 per sub-test) + JSON schema
|-- docs/
|   |-- PROPOSED_STANDARD.md
|   |-- ANTI_ANTHROPOMORPHIZATION_APPARATUS.md
|   `-- rater_training/
`-- tests/
    |-- unit/
    `-- integration/             live-endpoint probes (network required)
```

## Status

The harness CORE is production-ready: 5,592 LOC of Python, 151 unit tests passing, 5 live integration tests passing against real endpoints, 78 percent line coverage. Five sub-test plugins (KMR_ADV, ROT_5, BWD, APE_A, HRO) land production-grade with theoretical grounding, falsifiability criteria, and bootstrap CI scoring. A 150-item anchor pool ships with the repository.

KST v1.0 has been administered against the CAI.CI cognitive system as the first published baseline. v1.1 is in the work-queue, addressing the envelope-shape parser-anchor revision identified during the v1.0 run.

## How to cite

If you use KST in published work, please cite it via [CITATION.cff](CITATION.cff) or with the following:

```
Kari, A. (2026). KST: the Kari Sapience Test. Manceps, Inc.
https://github.com/manceps/kst
```

## Author and contact

Al Kari
Manceps, Inc.
research@manceps.com
https://github.com/manceps/kst

## License

MIT. See [LICENSE](LICENSE).
