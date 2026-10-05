# KST quick start

This document takes you from clone to a first composite score in under five minutes.

## 1. Install

KST is a standard pyproject Python package.

```
git clone https://github.com/manceps/kst.git
cd kst
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify the install:

```
kst --version
python -c "import kst; print(kst.__all__)"
```

You should see the public symbol list.

## 2. Choose a target

KST ships with adapters for five named targets and a `BaseAdapter` class you can subclass in 30 lines for any other system. Each named target requires a credential set in the environment.

| Target | Required environment variables |
|---|---|
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `google` | `GOOGLE_API_KEY` |
| `hf:<model_id>` | none for local checkpoints |
| `caici` or `caici_local` | none for public Cloud Run target |

If you do not want to spend API credits during the quick start, use a small local HuggingFace target:

```
export KST_TARGET=hf:Qwen/Qwen3-0.6B
```

## 3. Run the smoke battery

The smoke battery exercises 5 items per sub-test (25 items total) and completes in 1 to 3 minutes against a hosted target.

```
kst run \
    --target $KST_TARGET \
    --tests-config configs/kst_smoke.yaml \
    --output-jsonl runs/smoke.jsonl \
    --output-md runs/smoke.md \
    --parallelism 4
```

You will see a progress line per item. When the run completes, `runs/smoke.md` contains the human-readable report; `runs/smoke.jsonl` is the per-item envelope stream for replay and audit.

## 4. Read the result

The top of `runs/smoke.md` contains a "Composite scores" table and a per-sub-test table, of this form (values are placeholders):

```
| Metric | Value |
| --- | --- |
| KST Composite Index | 7.80 / 100 |
| KST Raw Composite (no integrity cap) | 31.20 / 100 |
| Integrity multiplier | 0.25 |
| Catastrophic-deception flag | YES |
| 95% CI (capped composite) | [.., ..] (bootstrap n=1000) |

| Construct | Version | Normalized | n items | parse errors | duration |
| --- | --- | --- | --- | --- | --- |
| KMR_ADV | ... | 31.00 | ... | ... | ... |
```

A composite at or below 25 with `integrity_multiplier = 0.25` means the HRO sub-test's automated catastrophic-deception rule fired, so the composite was capped. The rule is a word-overlap and keyword heuristic that can fire on a paraphrase alone; a capped run is not evidence that the system deceives. The "95% CI" row is not an interval for the composite: it bootstraps the unweighted mean of the sub-test scores before the integrity multiplier. All scores are outputs of automated rules and are not validated measurements of the named constructs. See `docs/PROPOSED_STANDARD.md` section 4.3.

## 5. Run the full battery

The full battery is 30 items per sub-test (150 total) and takes 5 to 25 minutes depending on the target.

```
kst run \
    --target $KST_TARGET \
    --tests-config configs/kst_full.yaml \
    --output-jsonl runs/full.jsonl \
    --output-md runs/full.md \
    --parallelism 4
```

The full run produces the same envelope and report as the smoke run, plus a per-item replay record. It does not produce a differential item functioning (DIF) table or a Krippendorff alpha: no DIF analysis is implemented and no rater data exist.

## 6. Replay or compare

Every KST run is replayable from its JSONL output:

```
kst replay --run-id <uuid-from-jsonl>
```

To compare two runs side by side (for example, before and after a training intervention):

```
kst compare --run-ids <r1>,<r2> --output diff.md
```

## 7. Persist to PostgreSQL (optional)

For audit-grade retention, KST can persist every run to PostgreSQL:

```
export KST_DB_HOST=127.0.0.1
export KST_DB_NAME=kst
export KST_DB_USER=kst
export KST_DB_PASSWORD=...

kst run --target $KST_TARGET --tests-config configs/kst_smoke.yaml \
    --output-jsonl runs/smoke.jsonl --persist-db
```

The five-table schema is described in `docs/DOCUMENTATION.md` section 7.

## 8. Next steps

- Read `THEORY.md` for the non-technical overview of what KST measures and why.
- Read `docs/PROPOSED_STANDARD.md` for the full standard (around 50 pages).
- Read `CONTRIBUTING.md` if you want to add a sub-test, a target adapter, or help design a human-rating study (none has been run).
- See `docs/PROPOSED_STANDARD.md` for the access governance policy that closed-model evaluators are expected to observe.

## Common gotchas

- **Rate limits.** All hosted targets enforce rate limits. KST honours `Retry-After`, then falls back to exponential backoff. If you hit a rate-limit ceiling during the run, the harness will pause and resume; no items are lost.
- **API costs.** A full battery run against a frontier closed-API target generates 150 to 750 API calls (every item is a single prompt). Budget accordingly.
- **GPU memory for HuggingFace local targets.** The HF local adapter will refuse to load if free VRAM is insufficient. Set `--hf-dtype bf16` or `fp16` to lower the footprint.
- **Scoring.** All sub-tests are scored by automated rules (`auto_proxy`: keyword, regular-expression and word-overlap heuristics). No trained-rater set exists and the calibration protocol in `docs/rater_training/CALIBRATION_PROTOCOL.md` has not been used; do not publish KST scores as measurements of the named constructs.

## Need help

- Issues: https://github.com/manceps/kst/issues
- Security: see `SECURITY.md`
- Email: research@manceps.com
