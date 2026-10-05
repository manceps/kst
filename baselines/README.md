# Published Baseline Runs

> **Status (October 2026).** No baseline report is published in this directory. Baseline figures that appeared elsewhere in this repository's history (for example in `CHANGELOG.md` and `docs/PROPOSED_STANDARD.md`) and the scores shown on the public KST dashboard are placeholder outputs of the automated scoring (keyword, regular-expression and word-overlap rules). Several pre-date scorer fixes, and none is a validated measurement of the named constructs.

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

- **Composite KST Index** with the raw composite and the integrity multiplier. (The harness's "95% CI" is not an interval for the composite; report it only with that caveat.)
- **Per-sub-test SubTestScores** (KMR-Adv, ROT-5, BWD, APE-A, HRO) (their CIs are fixed placeholders in v1.2.0 and should not be reported as intervals).
- **HRO integrity multiplier** and **catastrophic-deception flag**.
- **Anchor item counts** per sub-test and the **total wall-clock duration**.
- **Methodology version** under which the run was executed.
- **Rater mode** (in practice always `auto_proxy`, the automated scoring; no trained raters or rater cohorts exist).
- **Reproducibility envelope:** the harness commit SHA, the adapter target, and the seed used for bootstrap resampling.

The methodology takes no position on whether the scored system is phenomenally conscious. Composite scores are weighted aggregates of automated rule-based sub-test scores; they are not validated measurements of the named constructs and are not claims about machine experience.

## Submission

External baseline submissions are welcome. Open a pull request adding a `baselines/<system_name>/<date>_v<methodology>.md` document. The harness output JSON, the adapter configuration YAML, and the persistence-layer export should be attached as artifacts to the PR for reproducibility verification.
