"""Manifest writer / reader.

The manifest is the **single source of truth** for what's in the corpus.
Every later stage of the pipeline consults it:

  * Chunking (Step 3) only chunks documents that appear in the manifest.
  * Indexing (Step 4) keys ChromaDB collections on
    ``{corpus_version}_{manifest_sha256[:8]}`` so a corpus change forces a
    rebuild rather than silently mixing old and new chunks.
  * Citation existence checks (Step 6, ADR 0006 layer 3) verify that any
    cited ``(doc_id, section)`` pair exists in the manifest.

The manifest is JSON, sorted by ``doc_id`` for stability, and includes a
top-level ``manifest_sha256`` over the canonical entries blob so any
downstream consumer can detect drift cheaply.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from auth_rag.exceptions import IngestionError
from auth_rag.ingestion.models import Manifest, ManifestEntry

MANIFEST_FILENAME = "manifest.json"


def write_manifest(
    *,
    entries: Iterable[ManifestEntry],
    corpus_version: str,
    processed_dir: Path,
) -> Manifest:
    """Atomically write the manifest into ``processed_dir/manifest.json``.

    Returns the :class:`Manifest` that was written.
    """
    sorted_entries = tuple(sorted(entries, key=lambda e: e.doc_id))
    if not sorted_entries:
        raise IngestionError("refusing to write an empty manifest")

    canonical_blob = _canonical_blob(corpus_version, sorted_entries)
    manifest_sha256 = hashlib.sha256(canonical_blob.encode("utf-8")).hexdigest()
    manifest = Manifest(
        corpus_version=corpus_version,
        generated_at=datetime.now(UTC),
        entries=sorted_entries,
        manifest_sha256=manifest_sha256,
    )

    processed_dir.mkdir(parents=True, exist_ok=True)
    target = processed_dir / MANIFEST_FILENAME
    tmp = target.with_suffix(".json.part")
    tmp.write_text(
        manifest.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)
    return manifest


def read_manifest(processed_dir: Path) -> Manifest:
    """Load the manifest, validate it, and verify its ``manifest_sha256``.

    Raises:
        IngestionError: file missing, malformed, or hash mismatch.
    """
    target = processed_dir / MANIFEST_FILENAME
    if not target.is_file():
        raise IngestionError(f"manifest not found: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        manifest = Manifest.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise IngestionError(f"manifest is invalid: {target}") from exc

    canonical_blob = _canonical_blob(manifest.corpus_version, manifest.entries)
    expected = hashlib.sha256(canonical_blob.encode("utf-8")).hexdigest()
    if expected != manifest.manifest_sha256:
        raise IngestionError(
            f"manifest hash mismatch: stored={manifest.manifest_sha256} recomputed={expected}"
        )
    return manifest


def _canonical_blob(corpus_version: str, entries: tuple[ManifestEntry, ...]) -> str:
    """Stable serialization used for the top-level integrity hash.

    Includes ``corpus_version`` (so changing the corpus tag invalidates the
    hash) but excludes ``fetched_at`` (so re-running ``ingest`` on identical
    content reproduces the same manifest_sha256 — important for the CI
    rebuild gate in Step 4).
    """
    payload = {
        "corpus_version": corpus_version,
        "entries": [
            json.loads(entry.model_dump_json(exclude={"fetched_at"}, exclude_none=True))
            for entry in entries
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
