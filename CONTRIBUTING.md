# Contributing

Thanks for considering a contribution. Quick orientation:

## Setup

```bash
uv pip install -e ".[dev]"
pre-commit install
cp .env.example .env  # fill in if you want to run hosted models
```

## Loop

```bash
# Fast feedback before committing
ruff check . --fix
ruff format .
mypy src
pytest -m unit
```

## Conventions

- **Conventional commits.** `feat:`, `fix:`, `perf:`, `docs:`, `refactor:`,
  `test:`, `chore:`. Short subject + optional body explaining *why*.
- **One logical change per commit.** No batching unrelated edits.
- **One PR per roadmap step.** Smaller PRs review faster.
- **ADR for non-trivial design choices.** Add a new file under `docs/adr/`;
  update the index in `docs/adr/README.md`.
- **No secrets in commits.** `gitleaks` runs pre-commit and CI; rotate any
  key that ever lands in history.

## Tests

- Unit tests: must run in <5s total, no IO, no network. Mark with `@pytest.mark.unit`.
- Integration tests: real models, real ChromaDB, mocked LLM. `@pytest.mark.integration`.
- Eval tests: full RAGAS run; CI on PR-to-main only. `@pytest.mark.eval`.

## Code style

- Strict typing (`mypy --strict`). No `Any` without a justifying comment.
- Pydantic v2 models for any data crossing module boundaries.
- `pathlib.Path` over `os.path`.
- Logging via `auth_rag.logging_config.get_logger`, never `print`.
- Errors via the typed hierarchy in `auth_rag.exceptions`, never bare exceptions
  across module boundaries.
