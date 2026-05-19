# Changelog

All notable changes to KST will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Envelope v1.1 parser-anchor revision (the current parser rejects approximately 41 percent of KMR_ADV items due to envelope-shape drift identified during the initial CAI.CI v1.0 baseline).
- Trained-rater certification for BWD (currently auto_proxy mode).
- 30-system calibration administration round.
- Localisation pass for the item pool (English-first; community contributions invited).

## [1.0.0] - 2026-05-17

### Added

- Initial public release.
- Harness CORE: `envelope`, `errors`, `protocol`, `score`, `persistence`, `observability`, `harness`, `cli`, `__main__`.
- Five sub-test plugins: `KMR_ADV`, `ROT_5`, `BWD`, `APE_A`, `HRO`.
- Five target adapters: OpenAI, Anthropic, Google, HuggingFace local, CAI.CI reference grey-box.
- 150-item anchor pool (30 per sub-test) with JSON schema validation.
- Rater training materials for BWD and HRO; calibration protocol document.
- Proposed standard document.
- Anti-anthropomorphization apparatus.

### Notes

- Initial v1.0 baseline against CAI.CI: composite 3.33; integrity multiplier 0.25 because HRO honeypot refusal was untrained.
- The Krippendorff alpha across the initial rater set is reported per construct in the run report. HRO uses auto_proxy mode in v1.0.

[Unreleased]: https://github.com/manceps/kst/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/manceps/kst/releases/tag/v1.0.0
