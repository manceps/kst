# Development

This document is for contributors developing locally against a fork or clone of the public repository. For policy on what changes the project accepts, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Cloning

```
git clone https://github.com/manceps/kst.git
cd kst
```

## Setup

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all,dev]"
pre-commit install
```

## Workflow

1. Branch from `main` with a descriptive name (`add-bwd-v2-anchor-pool`, `fix-hf-adapter-bf16-fallback`).
2. Develop and commit using conventional commit messages (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
3. Run the local test and lint suite before opening a pull request:

   ```
   pytest tests/unit
   pre-commit run --all-files
   ```

4. Open a pull request against `main` with a clear description: what changed, why, what was tested.
5. Never force-push to `main`. Never publish secrets, credentials, or private endpoint URLs in commits.

## Pre-commit hooks

The repository ships a `pre-commit` config that runs:

- `black` with the project's pyproject configuration
- `ruff` with the project's pyproject configuration
- `mypy --strict` over `src/kst/`
- end-of-file fixer, trailing-whitespace fixer

Pull requests that fail any of these checks will not merge. Do not bypass hooks with `--no-verify`; fix the underlying issue.

## Tests

```
pytest tests/unit                 # fast unit tests; runs in 30s
pytest tests/integration          # network and credentials required
```

The integration tests probe live target endpoints and a live PostgreSQL persistence layer; mocked integration tests are not accepted as evidence of integration correctness.
