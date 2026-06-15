# ADR 0002 — Tooling: ruff + mypy + pre-commit + uv

- **Status:** Accepted
- **Date:** 2026-06-14

## Context

Tool sprawl (black + isort + flake8 + pylint) is the historic norm but is
slow, redundant, and a maintenance burden. The project must be cheap to lint
in CI and friction-free for new contributors.

## Decision

- **`ruff`** for both linting *and* formatting (replaces black, isort, flake8,
  pylint, pyupgrade). Single tool, sub-second runs.
- **`mypy`** in strict mode for type checking.
- **`pytest`** + `pytest-cov` with a 70% branch-coverage floor.
- **`pre-commit`** to enforce hooks locally before commits.
- **`uv`** as the package manager and resolver — 10–100× faster than pip and
  makes CI noticeably snappier.
- **`gitleaks`** in pre-commit and CI to prevent accidental secret commits.
- **`pip-audit`** in CI for known-CVE detection.
- **`deptry`** to flag undeclared / unused dependencies.

## Alternatives considered

1. **black + isort + flake8** — works, slow, three configs to maintain, three
   tools to teach contributors.
2. **Pyright over mypy** — faster, stricter. mypy chosen because it integrates
   better with `pydantic.mypy` and has wider editor support across IDEs in 2026.
3. **Poetry over uv** — feature-rich but slow installs. uv was chosen for raw
   speed and simpler `pyproject.toml`-only workflow.

## Consequences

- (+) One config (`pyproject.toml`) for almost everything.
- (+) CI lint runs in seconds, not minutes.
- (+) Strict mypy from day one — types are part of the design, not a retrofit.
- (−) `ruff` rule set is opinionated; some rules (e.g. `ANN`) require effort to
  comply with. Justified: type hints are non-negotiable.
- (−) `uv` is younger than pip/poetry; small risk of edge-case bugs. Mitigated
  by keeping `pyproject.toml` standards-compliant (PEP 621) so we can switch
  back to pip with no source changes.
