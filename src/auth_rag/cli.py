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
