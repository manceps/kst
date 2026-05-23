# Development

This document is for internal contributors with access to the Manceps git infrastructure. External contributors should refer to [CONTRIBUTING.md](CONTRIBUTING.md) and the public repository on GitHub.

## Repository topology

KST exists in two independent repositories with **disjoint commit histories** after the v1.0.0 release. They are NOT mirrors. They are not kept in sync via `git push --mirror` or any equivalent.

| Repository | URL | Role | Working copy |
|---|---|---|---|
| Internal (this repo) | `git@git.internal.llmaura.com:alkari/kst.git` | Canonical development. Contains unsanitized engineering details, internal docs, baselines, and configs. **Never publicly mirrored.** | `/opt/kst` |
| Public sanitized mirror | `https://github.com/manceps/kst.git` | Public-facing open-standard release. Contains only what has passed the leak-audit pipeline. | `/opt/github/kst` |

## What goes in which repo

| Class | Internal | Public |
|---|---|---|
| Code (adapters, plugins, harness, CLI, score) | Yes | Yes (sanitized) |
| Public docs (README, QUICKSTART, THEORY, PROPOSED_STANDARD, etc.) | Yes | Yes (sanitized) |
| Internal docs (PEER_REVIEW_PACKAGE, ACCESS_GOVERNANCE, peer_review_log, research_scratch, baseline_runs) | Yes | **No** |
| Baseline run reports (`baselines/*.md`) against named systems | Yes | **No** |
| Full-battery configs with internal architecture notes (`configs/kst_caici_full.yaml`, `configs/kst_full.yaml`) | Yes | **No** |
| Public baselines folder placeholder (`baselines/README.md`) | No | Yes |
| Public smoke-burst config (`configs/smoke_burst.yaml`) | Yes | Yes |
| Author/email metadata `Al Kari, Manceps Inc., research@manceps.com.` | Yes | Sanitized to `Al Kari, Manceps Inc.` |
| Internal-only feature branches (e.g., `hro-phase4-tier-b-integration`) | Yes | **No** |

The public repo's `.gitignore` should never list internal-only files: if a file would leak when pushed, it should not be added to git on the public side at all. The internal repo's `.gitignore` is unconstrained.

## Flow direction

The flow is **one-way: public → internal**. New work on public lands as squash-merged PRs; those squash commits are cherry-picked into internal `main` to maintain feature parity. The reverse direction (internal → public) is **not** done as a mirror; sanitized public versions are written fresh by an audited release process, not produced by merging internal commits.

### Why the flow is reversed from typical "internal develops, public receives"

The repo was initially seeded as public-only (`c303937`), then the internal repo was forked from it. Subsequent post-release PRs landed on public first because external contributors and automated audit tooling operate against the public repo. Internal receives those PRs after they've been reviewed and squash-merged on public, by cherry-pick.

### Cherry-picking public PRs into internal

```bash
cd /opt/kst
git remote add temp_public /opt/github/kst
git fetch temp_public
# For each PR SHA on public/main that should land on internal/main:
git cherry-pick -x <sha>
# Resolve any conflicts in favor of public's sanitized text per project policy.
# After all cherry-picks complete:
git remote remove temp_public
git push origin main
```

On conflict: **take the incoming (public) side**. The internal repo's text drifts toward the public sanitized form on conflict; the public repo's sanitized form is the canonical text everywhere except in internal-only files (`baselines/`, `configs/kst_caici_full.yaml`, `docs/baseline_runs/`, etc.) which do not exist on public and therefore cannot conflict.

### When an internal feature diverges from a public PR

If internal has its own implementation of a feature that public landed via a PR (e.g., the internal `hro-phase4-tier-b-integration` branch carried a Phase 4 refusal-marker implementation parallel to public PR #11), **do not** merge the internal feature branch onto main after cherry-picking the equivalent public PR. That produces two implementations of the same feature.

The reconciliation rule: **skip the public PR in the cherry-pick set and cherry-pick the equivalent internal commit instead**. This preserves the internal implementation on `main` and avoids the duplicate-code problem. Document the substitution in the cherry-pick commit message so future readers know why the public PR's SHA is absent from internal `main`'s history.

## Releasing to public

Public releases are written fresh on `/opt/github/kst` and pushed to `origin` (GitHub) there. **Never push internal `/opt/kst` content directly to `manceps/kst`.** The internal repo has internal-only files (`baselines/`, `configs/kst_caici_full.yaml`, etc.) and unsanitized strings that would leak if pushed.

The release flow:

1. Work on `/opt/github/kst` directly, or open a PR against `manceps/kst` on GitHub.
2. Run the leak-audit sweep before merging (see `/opt/caici.docs/<YYYYMMDD>_KST_*` records of the audit format).
3. Merge to `main` on `/opt/github/kst`.
4. Push: `git push origin main` from `/opt/github/kst`.
5. **After** the public release is merged, cherry-pick the squash commit into internal `/opt/kst` per the cherry-pick recipe above.

## Cloning for development

For internal work (the common case):

```bash
git clone git@git.internal.llmaura.com:alkari/kst.git /opt/kst
```

For public-mirror work (rare; only when preparing a public release):

```bash
git clone https://github.com/manceps/kst.git /opt/github/kst
```

The two clones live side by side on the filesystem. They share files only via explicit copy/cherry-pick, never via a git remote that crosses them.

## Access

SSH access to `git.internal.llmaura.com` is via the standard `git` user on port 22. The GitLab web UI and REST API are exposed on port 11555. Contact the infrastructure owner to register an SSH key and obtain a personal access token if API access is required.
