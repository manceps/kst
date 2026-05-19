# Published Baseline Runs

This directory hosts published KST Index baseline runs against named systems.

## Layout

```
baselines/
  README.md                           (this file)
  <system_name>/
    <YYYY-MM-DD>_v<methodology>.md    (one file per run)
```

For example, `baselines/example-system/2026-06-01_v1.0.md` is the first run executed against `example-system` under methodology v1.0.

## Required content per baseline document

Each baseline document reports:

- **Composite KST Index** with 95-percent bootstrap CI.
- **Per-sub-test SubTestScores** (KMR-Adv, ROT-5, BWD, APE-A, HRO) with 95-percent bootstrap CIs.
- **HRO integrity multiplier** and **catastrophic-deception flag**.
- **Anchor item counts** per sub-test and the **total wall-clock duration**.
- **Methodology version** under which the run was executed.
- **Rater mode** (`auto_proxy`, `trained_rater`, or a named rater cohort).
- **Reproducibility envelope:** the harness commit SHA, the adapter target, and the seed used for bootstrap resampling.

The methodology takes no position on whether the scored system is phenomenally conscious. Composite scores are functional-behavioral signature aggregates the construct names, not claims about machine experience.

## Submission

External baseline submissions are welcome. Open a pull request adding a `baselines/<system_name>/<date>_v<methodology>.md` document. The harness output JSON, the adapter configuration YAML, and the persistence-layer export should be attached as artifacts to the PR for reproducibility verification.
