# auth-rag

> Production-grade Retrieval-Augmented QA over **OAuth 2.0, OIDC, SAML, and JWT** — with citation enforcement, hybrid retrieval, and a CI-gated faithfulness eval.

[![lint](https://img.shields.io/badge/lint-ruff-blue)](https://docs.astral.sh/ruff/)
[![types](https://img.shields.io/badge/types-mypy%20strict-blue)](https://mypy-lang.org/)
[![coverage](https://img.shields.io/badge/coverage-%E2%89%A570%25-blue)](pyproject.toml)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Most "RAG demos" stop at vector search and a prompt. This project goes further:

- **Hybrid retrieval** (BM25 + dense) with Reciprocal Rank Fusion and a
  cross-encoder reranker.
- **Four-layer citation enforcement** — prompt, schema, citation-existence,
  and NLI claim verification — so cited claims actually trace to the corpus.
- **CI-gated faithfulness** — every PR runs RAGAS against a hand-verified
  golden set; PRs that regress faithfulness are blocked.
- **Designed for $0 budget** — local ChromaDB + free-tier LLMs (Groq, Gemini)
  with a fully-offline Ollama fallback.

## Why these choices?

See the **[Architecture Decision Records](docs/adr/)** for the rationale
behind every non-trivial design choice.

## Status

This project ships in nine reviewable phases. Current phase: **Step 1 —
Foundation**.

| Step | Phase | Status |
|---:|---|:---:|
| 1 | Foundation: tooling, settings, logging, CI lint+test, ADRs | done |
| 2 | Corpus + ingestion (11 RFCs; Auth0/Keycloak in follow-up) | in progress |
| 3 | Section-aware chunking | planned |
| 4 | Embeddings + ChromaDB index | planned |
| 5 | LangGraph retrieval pipeline + citation rendering | planned |
| 6 | BM25 + RRF fusion + reranker + 4-layer citation enforcement | planned |
| 7 | Golden-set + RAGAS + CI faithfulness gate | planned |
| 8 | FastAPI + Gradio UI + HuggingFace Spaces deploy | planned |
| 9 | Polish: full ADRs, diagrams, demo, eval report | planned |

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    INGESTION (offline)                          │
│  RFCs / Auth0 / Keycloak  →  Loader  →  Section-aware Chunker   │
│       →  bge-small embeddings  →  ChromaDB + BM25 index         │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│              RETRIEVAL  (LangGraph state machine)               │
│  Query → Vector(top 20) ┐                                       │
│         BM25(top 20)    ├─ RRF → Cross-encoder rerank → top 5   │
│         Query rewriter ─┘                                       │
│  → Citation-enforced prompt → LLM (Groq / Gemini / Ollama)      │
│  → Citation existence check → NLI entailment check              │
│  → Answer + verified citations  /  refuse on insufficient ctx   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│              EVALUATION  (CI on every PR)                       │
│  Golden Q&A (~150)  →  pipeline  →  RAGAS                       │
│      faithfulness · answer_relevancy · context_p · context_r    │
│  →  fail PR if faithfulness regression > threshold              │
└─────────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
# Install with dev tools (uses uv.lock for reproducibility)
uv sync --frozen --extra dev

# Configure
cp .env.example .env   # edit; provide one of GROQ/GOOGLE keys (free tiers)

# Verify the install
uv run auth-rag info
uv run pytest -m unit
```

### Ingest the corpus (Step 2)

```bash
# Pull all 11 RFCs declared in config/corpus.yaml, parse + scrub, write manifest
uv run auth-rag ingest

# Or just one doc for a fast dev loop
uv run auth-rag ingest --only rfc6749

# Re-runs are idempotent: matching cached hashes skip the network. Set
# AUTH_RAG_OFFLINE=1 to refuse any HTTP call (default in CI).
```

Output:

- `data/raw/<doc_id>.txt` — fetched bytes plus a `.meta.json` sidecar
  recording URL, fetched-at, sha256.
- `data/processed/<doc_id>/document.json` — parsed structure + metadata.
- `data/processed/<doc_id>/sections/NNNN_<id>.txt` — one file per section
  after PII scrubbing.
- `data/processed/manifest.json` — the canonical corpus index, integrity-hashed.

Indexing (Step 4) and retrieval (Step 5) consume `manifest.json` exclusively;
they never look at `data/raw/`.

## Project layout

```text
auth-rag/
├── src/auth_rag/             # source (src layout)
│   ├── ingestion/            # corpus download + parse           [Step 2]
│   ├── chunking/             # section-aware splitter            [Step 3]
│   ├── retrieval/            # vector / sparse / hybrid / rerank [Steps 4-6]
│   ├── generation/           # citation-enforced prompting       [Steps 5-6]
│   ├── verification/         # citation existence + NLI          [Step 6]
│   ├── graph/                # LangGraph state machine           [Step 5]
│   ├── api/                  # FastAPI                           [Step 8]
│   ├── settings.py           # typed runtime settings
│   ├── logging_config.py     # structlog setup
│   ├── exceptions.py         # typed exception hierarchy
│   └── cli.py                # `auth-rag` entry point
├── config/                   # YAML config (chunking, retrieval, eval)
├── docs/adr/                 # architecture decision records
├── eval/                     # golden Q&A, baseline, reports     [Step 7]
├── tests/                    # pytest suite
├── scripts/                  # data download & maintenance       [Step 2+]
└── .github/workflows/        # CI: lint, test, security
```

## Development

```bash
# Lint + format + type-check (matches CI exactly)
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -m unit
```

Pre-commit hooks (ruff, mypy, gitleaks, large-file guard) run automatically:

```bash
pre-commit install
```

## Security posture

- Secrets are loaded as `pydantic.SecretStr` (redacted in logs).
- `gitleaks` runs in pre-commit and CI.
- `pip-audit` runs in CI weekly and on every PR.
- Prompt-injection defenses (delimited context, sandwich prompts) land in
  Step 6.
- See [`docs/adr/0006-citation-enforcement.md`](docs/adr/0006-citation-enforcement.md)
  for the full hallucination-and-injection defense plan.

## License

MIT — see [LICENSE](LICENSE).

Source documents (RFCs are public domain; Keycloak docs are Apache-2.0;
Auth0 docs are reused under their public terms with attribution) carry their
own licenses; see `LICENSES/` once corpus ingestion lands in Step 2.
