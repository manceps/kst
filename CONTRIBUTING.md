# Contributing to KST

Thanks for considering a contribution. KST is published as a candidate industry standard and is intended to evolve through community input, expert critique, and reproducible empirical evidence.

This document describes how to propose changes, what we accept, and what the bar is for inclusion.

## Code of Conduct

This project adopts the Contributor Covenant 2.1. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Participation in this project means agreement to abide by it.

## Where to start

| You want to | Start here |
|---|---|
| Report a bug in the harness or a plugin | Open a GitHub issue with `bug` label |
| Propose a new sub-test plugin | Open a `proposal: sub-test` issue first; do not open a PR before consensus |
| Propose a new target adapter | Open a PR; small adapters can land directly |
| Contribute rater labels for the trained-rater set | See "Rater contributions" below |
| Challenge an existing sub-test's validity | Open a `challenge: <construct>` issue with a position paper |
| Improve documentation, typos, examples | Open a PR directly |
| Add a translation of the item pool | Open a `proposal: localisation` issue first |

## Bar for inclusion

KST is bound by an explicit no-MVP no-scaffolding standard: every line of code, every sub-test, every adapter that lands must be production-ready and audit-pack defensible on day one. We do not accept placeholder implementations, TODO-marked stubs, or "good enough for now" framing.

Concretely, a sub-test plugin landing in KST must:

1. Cite at least two papers as theoretical grounding. Cite the strongest available sources; preference for primary sources over review articles.
2. State at least one falsifiability criterion: a published condition under which a rater is licensed to mark a system "fail this construct."
3. Ship a 30-item anchor pool with the same JSON schema as the existing anchor pools (`data/item_pool/schema.json`).
4. Pass `validate_plugin(plugin)` without contract violations.
5. Have a parse_response implementation that handles malformed responses by raising `ScoreValidationError`, not by silent default.
6. Have a score implementation with a bootstrap CI computed across the item set.
7. Ship with at least 80 percent line coverage in `tests/unit/plugins/test_<construct>.py`.
8. Land alongside a sub-section in `docs/PROPOSED_STANDARD.md` describing the construct, the operationalisation, the rubric, the rater training note, and the limitations.

A target adapter landing in KST must:

1. Subclass `kst.adapters.base.BaseAdapter` (do not re-implement retry / backoff math).
2. Declare its `AdapterCapabilities` accurately. A sub-test that needs a capability not declared will produce `IncompleteBatteryError`, not a silent skip.
3. Pin the target model version explicitly in the example config. KST scores are not comparable across silent model upgrades.
4. Handle `Retry-After` headers and 429 / 5xx with the inherited backoff.
5. Pass a live integration test in `tests/integration/` against the actual hosted endpoint, gated on a credential environment variable so CI can skip when credentials are absent.
6. Document the cost envelope per full battery run in the adapter's docstring.

## Development setup

```
git clone https://github.com/manceps/kst.git
cd kst
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all,dev]"
pre-commit install
```

Run the test suite:

```
pytest tests/unit                 # fast unit tests; runs in 30s
pytest tests/integration          # network and credentials required
```

The repository ships a `pre-commit` config that runs:

- `black` with the project's pyproject configuration
- `ruff` with the project's pyproject configuration
- `mypy --strict` over `src/kst/`
- end-of-file fixer, trailing-whitespace fixer

PRs that fail any of these checks will not merge.

## Pull request workflow

1. Fork the repository.
2. Branch from `main` with a descriptive name (`add-bwd-v2-anchor-pool`, `fix-hf-adapter-bf16-fallback`).
3. Write the change, including tests. New code without tests is not accepted; bug fixes without a regression test that fails before the fix and passes after the fix are not accepted.
4. Run the local test and lint suite. PRs failing CI will be marked needs-fix; please do not push more commits to a failing branch without addressing the failures.
5. Open a PR with a clear description: what changed, why, what was tested.
6. Respond to review comments within a reasonable window. PRs idle longer than 30 days may be closed (the work is not lost; reopen when ready).
7. Squash-merge is the default. The squashed commit message should be a conventional commit (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).

Do not skip pre-commit hooks (`--no-verify`) or sign-off bypasses (`--no-gpg-sign`). If a hook fails, investigate; do not bypass.

## Rater contributions

The trained-rater set is the most important external contribution to KST. To contribute as a rater:

1. Read `docs/rater_training/CALIBRATION_PROTOCOL.md` end to end.
2. Read the construct-specific manual for the sub-tests you intend to rate (`docs/rater_training/BWD_RATER_MANUAL.md`, etc.).
3. Complete the calibration protocol against the 30-item anchor pool for that sub-test. Submit your ratings via the rater-onboarding form (linked in the protocol document).
4. Reach the calibration threshold (Krippendorff alpha >= 0.7 against the gold-standard ratings).
5. Once certified, your ratings become part of the published rater set for that sub-test.

Rater contributions are credited (with consent) in `docs/PEER_REVIEW_PACKAGE.md` and in the per-run rater attribution recorded in the persistence layer.

## Sub-test proposal process

A sub-test addition is consequential, because once a sub-test is in the standard, downstream consumers rely on its stability. The process:

1. Open a `proposal: sub-test` issue with: construct name, theoretical grounding (papers), proposed operationalisation, sample items (5 to 10), proposed falsifiability criterion, and proposed scoring rubric.
2. The proposal is open for comment for a minimum of 14 days. Maintainers and the existing rater pool are notified.
3. If consensus emerges, a draft PR is invited. The PR must satisfy all eight requirements above.
4. After PR review, if accepted, the sub-test lands behind a `v0` version tag for one minor release cycle, during which its construct_id is published but its score is annotated "experimental" in the run report.
5. After the experimental cycle, if the construct is judged stable, it is promoted to `v1`.

Removing or renaming an existing sub-test follows the same process in reverse, with an additional six-month deprecation cycle.

## Challenge process

A serious critique of an existing sub-test, the integrity multiplier, the aggregation method, or the rater protocol is welcome. Open a `challenge: <topic>` issue with:

- the specific claim you are challenging
- the evidence or argument you are presenting
- the change you propose (if any)

Challenges are open for comment, and the maintainers commit to a written response within 30 days. If a challenge results in a standard revision, the change is recorded in `CHANGELOG.md` with attribution.

## Out of scope

KST does not accept contributions that:

- Implement self-evaluation loops (a system rating its own KST score)
- Add reward signals derived from KST for use in RL training (KST is a measurement protocol, not a training signal)
- Add benchmarks for closed-form skills (reasoning, code, math) without an explicit sapience-marker operationalisation
- Add adapters for systems where the model identity cannot be pinned and reproducibility cannot be defended

If your contribution falls in one of these categories, please open a discussion first; we can usually identify an in-scope contribution that addresses the underlying motivation.

## License

By contributing, you agree that your contributions will be licensed under the MIT License (see [LICENSE](LICENSE)).

## Contact

For questions that do not fit the issue tracker:

research@manceps.com
