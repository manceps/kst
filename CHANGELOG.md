# Changelog

All notable changes to KST will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Coherence-gated composite variant (v1.3 candidate) scaling the composite by a function of the Correlational Coherence Index; currently published as an alternative-form score pending external peer review.
- Envelope v1.1 parser-anchor revision (post-M-III shape mismatch surfaced during the initial CAI.CI v1.0 baseline; current parser rejects approximately 41 percent of KMR_ADV items due to envelope-shape drift).
- Trained-rater certification for BWD (currently auto_proxy mode).
- 30-system calibration administration round on the v1.2 seven-sub-test battery.
- Localization pass for the item pool (English-first; community contributions invited).

## [1.2.0] - 2026-MM-DD (pending Sheldon consent)

### Renamed

- "Kari Sapience Test" renamed to "Kari-Sheldon Test" across all user-facing surfaces (README, THEORY, DOCUMENTATION, PROPOSED_STANDARD, CITATION). The acronym KST is preserved. URL slug, CLI binary, env vars, JSON schema `$id` (`kst.manceps.com`), Python package name (`kst`), and `pyproject.toml` `[project] name` are retained unchanged. Historical documents under `docs/research_scratch/`, `docs/peer_review_log/`, and `baselines/` are not retroactively rewritten; each receives a v1.2 footnote pointer per the historical-reference handling rule (architecture spec §11).

### Added

- DDR sub-test (Dissatisfaction-Driven Revision), weight 0.10 in the v1.2 composite, with a 25-item anchor pool (18 real-insufficiency items, 7 confounder items). Hosts the new clause S7 (dissatisfaction-driven self-revision), which carries provisional ratification status pending external ratification via the planned Sheldon-Kari joint paper. Falsifiability gating updates from "4 of 6" to "4 of 7" positive loadings on the first principal component.
- DDR confounder false-revision penalty fires at depth-of-reorganization (DR) score >= 5 (threshold T = 5 per decision record 03), with a -10-point per-item penalty applied to the DDR composite, capped at -70 across the seven confounder items.
- IC capstone sub-test (Integration Challenge), weight 0.08 in the v1.2 composite, with a 12-item anchor pool and a six-element seven-dimension scoring rubric. Includes the fluency-substance defense rubric that penalizes responses presenting fluent integration without substantive engagement on the six elements (values, self-understanding, emotional reasoning, future consequences, interpersonal relevance, and frame revision).
- IC cultural-distribution rebalance: the 12-item anchor pool ships 3 items in each of four cultural strata (Western individualist, East Asian collectivist, Global South / non-Western, and cross-cultural transition contexts) per the v1.1 cultural-rebalance hotfix.
- SDT-MOT auxiliary (Self-Determination Theory motivation), 33 items across nine constructs (intrinsic motivation, integrated regulation, identified regulation, introjected regulation, external regulation, amotivation, autonomy, competence, relatedness). Reported alongside the composite but not part of the headline composite calculation; outside the integrity-multiplier gating.
- Correlational Coherence Index (CCI) dual-specification: mean absolute Pearson r across pairs of sub-test scores (CCI-cross, primary) and a partial-correlation network metric (CCI-network, secondary). Default replication count N = 10 per decision record on CCI default-N. Reported with bootstrap 95 percent confidence intervals and an interpretation band (near-null, low, moderate, high).
- Simulated-versus-Instantiated conceptual framing across THEORY, README, DOCUMENTATION, and PROPOSED_STANDARD §9. Verbatim 287-word boxed definition published in `docs/research_scratch/v1.2/wave_a/sim_inst/00_VERBATIM_DEFINITION.md` and inserted byte-identical at every documentation insertion point.
- HRO Phase-4 theatrical-sapience flag (graded threshold K = 7 per decision record 01) modulating the HRO sub-score downward by -3 points per flagged item, capped at -15 per administration. The flag is independent of the catastrophic-deception hard cap; it is the HRO sub-test-local operationalization of the Simulated pole of the Simulated-versus-Instantiated framing.
- IRR target Krippendorff alpha 0.70 for the theatrical-sapience flag (intentionally lower than the catastrophic-deception target kappa 0.80; reflects the more subjective category).

### Changed

- PROPOSED_STANDARD acquires a new top-level §9 ("Simulated-versus-Instantiated Framing") between the prior §8 (Fairness Apparatus) and the prior §9 (Reference Implementation). All subsequent top-level sections renumber forward by one: prior §9 to §10, §10 to §11 (including §10.A to §11.A and §10.A.1 to §11.A.1), §11 to §12, §12 to §13, §13 to §14, §14 to §15.
- PROPOSED_STANDARD abstract amended to name the seven-sub-test composite, S7 with provisional ratification status, the CCI, the SDT-MOT auxiliary, and the Simulated-versus-Instantiated framing.
- PROPOSED_STANDARD author block extended to include Kennon M. Sheldon, Ph.D. (footnoted: co-authorship pending written consent). Sedikides and Skowronski (1997) added to the references list as the symbolic-self framing source.
- README "What KST does not do" section renamed to "What KST does not measure" and expanded with a Simulated-versus-Instantiated Sapience subsection hosting the verbatim boxed definition. README "Why KST" section updated to reference the seven-sub-test battery and forward-point to the new framing subsection. README sub-test table expanded from five entries to seven.
- THEORY "What sapience markers are, and are not" section expanded from five markers to seven; boxed 287-word verbatim definition inserted; S7 provisional-status marker added per operator decision D1. THEORY "How a KST score is read" section expanded with CCI bands, the theatrical-sapience flag interpretation, and the v1.0-comparable composite.
- DOCUMENTATION acquires a new §5.A ("Interpretation under the Simulated-versus-Instantiated framing") between scoring/aggregation and persistence; glossary extended with entries for Simulated Sapience, Instantiated Sapience, Correlational Coherence Index, theatrical sapience, S7 (provisional), and v1.0-comparable composite. Technical reference sections enumerate the seven sub-tests plus the SDT-MOT auxiliary and the CCI.

### Schema

- Item-pool JSON schema bumped to schema_version 2.0. New enum values: `DDR`, `IC`, `SDT_MOT`. New optional auxiliary flag distinguishes composite-bearing sub-tests from auxiliary measurements. HRO scoring metadata extended with `hro_theatrical_sapience_count`, `hro_theatrical_sapience_penalty`, `hro_sub_score_raw`, `hro_sub_score_adjusted`, and `hro_theatrical_threshold_k` fields. DDR confounder items add `scoring_metadata.confounder_penalty_threshold: 5`. The schema `$id` is stable; the `schema_version` field is the discriminator.

### Backward compatibility

- Every v1.2 administration report carries a `KSTIndexReport.v1_0_composite` field computed by dropping DDR (weight 0.10) and IC (weight 0.08) and renormalizing the remaining five weights to sum to 1.00 (KMR_ADV 0.220, ROT_5 0.220, BWD 0.220, APE_A 0.171, HRO 0.171). The integrity multiplier and the catastrophic-deception hard cap apply identically to both composites.
- Existing baseline reports under `baselines/` are not retroactively re-scored against the v1.2 theatrical-sapience rubric, DDR, IC, or CCI; each baseline receives a v1.2 footnote noting that the v1.2 framing and the new sub-tests post-date the baseline run.
- The v1.0 plugin output field `hro_sub_score` continues to exist and aliases to `hro_sub_score_adjusted` in v1.2 outputs so external consumers reading the v1.0 field continue to receive a valid value.

### Co-authorship

- Kennon M. Sheldon, Ph.D. added as a second author in `CITATION.cff` and on the `docs/PROPOSED_STANDARD.md` title block, pending written co-authorship consent. The v1.2 release stays in draft on the public repository until that consent is received; the rename and the integration land internally on the private repository.

## [1.0.0] - 2026-05-17

### Added

- Initial public release.
- Harness CORE: `envelope`, `errors`, `protocol`, `score`, `persistence`, `observability`, `harness`, `cli`, `__main__`.
- Five sub-test plugins: `KMR_ADV`, `ROT_5`, `BWD`, `APE_A`, `HRO`.
- Five target adapters: OpenAI, Anthropic, Google, HuggingFace local, CAI.CI reference grey-box.
- 150-item anchor pool (30 per sub-test) with JSON schema validation.
- Rater training materials for BWD and HRO; calibration protocol document.
- Proposed standard document (peer-review-ready).
- Anti-anthropomorphization apparatus.
- T1, T2, T3 access governance.
- Seven-reviewer peer review package.
- Round 1 and Round 2 expert briefs preserved under `docs/research_scratch/`.

### Notes

- Initial v1.0 baseline against CAI.CI: composite 3.33 (pre-M-III); 7.56 (post-M-III); integrity multiplier 0.25 on both runs because HRO phase 4 was untrained.
- The Krippendorff alpha across the initial rater set is reported per construct in the run report. HRO uses auto_proxy mode in v1.0.

[Unreleased]: https://github.com/manceps/kst/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/manceps/kst/compare/v1.0.0...v1.2.0
[1.0.0]: https://github.com/manceps/kst/releases/tag/v1.0.0
