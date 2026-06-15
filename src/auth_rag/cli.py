"""Command-line entry point.

Subcommands are added incrementally as features land:

    Step 2: ``ingest``       (corpus download + parse)
    Step 4: ``build-index``  (chunk + embed + persist)
    Step 5: ``ask``          (interactive query)
    Step 7: ``eval``         (run RAGAS suite)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from auth_rag._version import __version__
from auth_rag.logging_config import configure_logging, get_logger


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auth-rag",
        description="RAG over auth/identity protocols.",
    )
    parser.add_argument("--version", action="version", version=f"auth-rag {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    info = sub.add_parser("info", help="Print resolved settings (secrets redacted).")
    info.set_defaults(func=_cmd_info)

    ingest = sub.add_parser(
        "ingest",
        help="Download, parse, scrub, and write the corpus manifest.",
    )
    ingest.add_argument(
        "--config",
        type=Path,
        default=Path("config/corpus.yaml"),
        help="Path to corpus.yaml (default: config/corpus.yaml).",
    )
    ingest.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="DOC_ID",
        help="Restrict ingestion to one or more doc_ids (repeatable).",
    )
    ingest.set_defaults(func=_cmd_ingest)

    chunk = sub.add_parser(
        "chunk",
        help="Chunk the ingested corpus into retrieval-ready units.",
    )
    chunk.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="DOC_ID",
        help="Restrict chunking to one or more doc_ids (repeatable).",
    )
    chunk.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Target chunk size in tokens (default: 512).",
    )
    chunk.add_argument(
        "--chunk-overlap",
        type=int,
        default=64,
        help="Overlap between successive chunks in tokens (default: 64).",
    )
    chunk.set_defaults(func=_cmd_chunk)

    return parser


def _cmd_info(_: argparse.Namespace) -> int:
    from auth_rag.settings import get_settings  # noqa: PLC0415 - lazy import for fast --version

    settings = get_settings()
    log = get_logger(__name__)
    log.info(
        "settings.resolved",
        env=settings.env.value,
        embedding_model=settings.embedding_model,
        reranker_model=settings.reranker_model,
        generation_provider=settings.generation_provider.value,
        generation_model=settings.generation_model,
        data_dir=str(settings.data_dir),
        index_dir=str(settings.index_dir),
        groq_key_set=settings.groq_api_key is not None,
        google_key_set=settings.google_api_key is not None,
    )
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from auth_rag.ingestion import ingest, load_corpus_config  # noqa: PLC0415
    from auth_rag.settings import get_settings  # noqa: PLC0415

    settings = get_settings()
    log = get_logger(__name__)
    config_path = args.config if args.config.is_absolute() else settings.repo_root() / args.config
    config = load_corpus_config(config_path)
    manifest = ingest(
        config=config,
        raw_dir=settings.data_dir / "raw",
        processed_dir=settings.data_dir / "processed",
        only=args.only,
    )
    log.info(
        "ingest.cli.done",
        n_entries=len(manifest.entries),
        manifest_sha256=manifest.manifest_sha256,
        corpus_version=manifest.corpus_version,
    )
    return 0


def _cmd_chunk(args: argparse.Namespace) -> int:
    from auth_rag.chunking import ChunkingConfig, chunk_corpus  # noqa: PLC0415
    from auth_rag.settings import get_settings  # noqa: PLC0415

    settings = get_settings()
    log = get_logger(__name__)
    config = ChunkingConfig(
        chunk_size_tokens=args.chunk_size,
        chunk_overlap_tokens=args.chunk_overlap,
    )
    manifest = chunk_corpus(
        config=config,
        processed_dir=settings.data_dir / "processed",
        chunked_dir=settings.data_dir / "chunked",
        only=args.only,
    )
    log.info(
        "chunk.cli.done",
        n_docs=len(manifest.entries),
        n_chunks_total=sum(e.n_chunks for e in manifest.entries),
        chunk_manifest_sha256=manifest.chunk_manifest_sha256,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    func = args.func
    return int(func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
