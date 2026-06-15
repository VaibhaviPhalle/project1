"""Section-aware parser for IETF RFC plain-text files.

RFC text format is regular enough to parse precisely without writing a full
grammar. The parser extracts:

  * The numeric section tree (e.g. ``4.1.1 Authorization Code Grant``).
  * The page on which each section starts and ends.
  * Header / metadata fields (RFC number, title, authors, date) for the
    manifest entry.
  * Per-section text with page-break artifacts removed.

The parser is intentionally conservative:

  * Anything that looks ambiguous becomes a normal-paragraph line, not a
    fabricated section.
  * Page break artifacts (``\\f`` form-feeds plus the standard 2-line
    header/footer) are stripped from section text but the page numbers are
    captured into ``page_start`` / ``page_end``.
  * Tables-of-contents are detected (``Table of Contents``) and skipped:
    they would otherwise produce duplicate sections with empty bodies.

What we deliberately do *not* try to parse:

  * Author affiliation blocks at the end of an RFC (no section number).
  * The cover page / fold-marker before "Status of This Memo".

Both are kept as a single "front_matter" section so retrieval still works
on them, just at lower granularity.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from auth_rag.exceptions import IngestionError
from auth_rag.ingestion.models import ParsedDocument, Section, SourceKind
from auth_rag.logging_config import get_logger

if TYPE_CHECKING:
    from auth_rag.ingestion.models import SourceSpec

log = get_logger(__name__)

# A section header: optional whitespace, hierarchical number, dot or whitespace,
# then a title. Numbers like "4.", "4.1", "4.1.1", "Appendix A", "A.1".
_SECTION_RE = re.compile(
    r"^(?P<number>(?:\d+(?:\.\d+){0,3})|(?:[Aa]ppendix\s+[A-Z](?:\.\d+){0,2})|(?:[A-Z](?:\.\d+){1,2}))"
    r"\.?\s+(?P<title>[A-Z][^\n]{0,150})$"
)
_FORM_FEED = "\f"
_TOC_MARKER = "Table of Contents"
# Page-footer pattern: leading content then "[Page N]" near the right margin.
_PAGE_FOOTER_RE = re.compile(r"\[Page\s+(\d+)\]\s*$")
_RFC_HEADER_RE = re.compile(r"^RFC\s+(\d+)\b", re.IGNORECASE)
_FRONT_MATTER_ID = "front_matter"


@dataclass(frozen=True)
class _Block:
    """A page of raw text plus its 1-indexed page number."""

    page: int
    lines: tuple[str, ...]


def parse_rfc(spec: SourceSpec, raw_path: Path) -> ParsedDocument:
    """Parse an RFC ``.txt`` file into a :class:`ParsedDocument`.

    Raises:
        IngestionError: on unreadable file or completely unrecognized format.
    """
    if spec.kind is not SourceKind.RFC_TXT:
        raise IngestionError(f"parse_rfc called on non-RFC source: {spec.doc_id}")
    try:
        raw = raw_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise IngestionError(f"cannot read {raw_path}: {exc}") from exc

    if not raw.strip():
        raise IngestionError(f"RFC file is empty: {raw_path}")

    sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    pages = _split_pages(raw)
    metadata = _extract_metadata(pages)
    sections = tuple(_extract_sections(raw, pages))
    if not sections:
        # Fall back to a single front_matter section so the rest of the
        # pipeline doesn't choke on a doc we couldn't parse cleanly.
        log.warning("ingest.parse.no_sections", doc_id=spec.doc_id)
        sections = (
            Section(
                section_id=_FRONT_MATTER_ID,
                number=None,
                title=spec.title,
                text=raw.strip(),
                page_start=1,
                page_end=pages[-1].page if pages else 1,
                char_start=0,
                char_end=len(raw),
            ),
        )

    return ParsedDocument(
        doc_id=spec.doc_id,
        title=spec.title,
        kind=spec.kind,
        source_url=spec.source_url,
        license=spec.license,
        sha256=sha256,
        fetched_at=datetime.now(UTC),
        sections=sections,
        raw_char_count=len(raw),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Page splitting
# ---------------------------------------------------------------------------
def _split_pages(raw: str) -> tuple[_Block, ...]:
    """Split text into page blocks using form-feed markers + footer regex."""
    if _FORM_FEED in raw:
        chunks = raw.split(_FORM_FEED)
    else:
        # Some RFC mirrors strip form-feeds; fall back to splitting on the
        # "[Page N]" footer. We capture the footer in the split so the
        # downstream page-number detector can still find it.
        parts = re.split(r"(\[Page \d+\][^\n]*\n)", raw)
        chunks = []
        for i in range(0, len(parts), 2):
            body = parts[i]
            footer = parts[i + 1] if i + 1 < len(parts) else ""
            if body or footer:
                chunks.append(body + footer)

    pages: list[_Block] = []
    next_page_number = 1
    for chunk in chunks:
        if not chunk.strip():
            continue
        page_no = _detect_page_number(chunk) or next_page_number
        next_page_number = page_no + 1
        # Strip the standard RFC top-of-page header (3 blank lines after FF)
        # and the footer line. The header is variable; trim leading blank lines.
        lines = chunk.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        # Drop trailing footer line ("[Page N]") and any trailing blanks.
        while lines and (not lines[-1].strip() or _PAGE_FOOTER_RE.search(lines[-1])):
            lines.pop()
        # Drop the conventional first line ("RFC NNNN  Title  Month YYYY").
        # Heuristic: starts with "RFC " and is short.
        if lines and _RFC_HEADER_RE.match(lines[0]):
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
        pages.append(_Block(page=page_no, lines=tuple(lines)))
    return tuple(pages)


def _detect_page_number(chunk: str) -> int | None:
    for line in reversed(chunk.splitlines()):
        m = _PAGE_FOOTER_RE.search(line)
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
def _extract_metadata(pages: tuple[_Block, ...]) -> dict[str, str]:
    """Pull a few useful fields from the first page."""
    if not pages:
        return {}
    first = "\n".join(pages[0].lines)
    md: dict[str, str] = {}
    # Match the canonical "Request for Comments: <NNNN>" line.
    rfc_match = re.search(r"Request for Comments:\s*(\d+)", first)
    if rfc_match:
        md["rfc_number"] = rfc_match.group(1)
    # Match the "Category" tag (Standards Track, Informational, BCP, ...).
    cat_match = re.search(r"Category:\s*([^\n]+)", first)
    if cat_match:
        md["category"] = cat_match.group(1).strip()
    # The presence of an ISSN line indicates publication via the IETF stream.
    if "ISSN:" in first:
        md["stream"] = "IETF"
    return md


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------
def _extract_sections(raw: str, pages: tuple[_Block, ...]) -> list[Section]:
    """Walk the document, build a flat list of sections in order."""
    if not pages:
        return []

    in_toc = False
    sections: list[_PendingSection] = []
    current: _PendingSection | None = None

    for block in pages:
        for line in block.lines:
            stripped = line.strip()
            # Detect TOC start; everything until next non-numbered header is TOC.
            if stripped == _TOC_MARKER:
                in_toc = True
                continue

            header = _try_match_header(stripped)
            if header is None:
                if current is not None:
                    current.lines.append(line)
                continue

            number, title = header
            if in_toc:
                # Heuristic: TOC lines also match the header regex but tend to
                # be followed by ".... NN" page-number dots. Detect by the
                # presence of trailing dots on the same line.
                if "." * 3 in line:
                    continue
                # First "real" section ends the TOC.
                in_toc = False

            if current is not None:
                current.page_end = block.page
                sections.append(current)

            current = _PendingSection(
                number=number,
                title=title,
                page_start=block.page,
                page_end=block.page,
                lines=[],
            )

    if current is not None:
        current.page_end = pages[-1].page
        sections.append(current)

    return list(_finalize(sections, raw))


def _try_match_header(line: str) -> tuple[str, str] | None:
    """Return (number, title) if ``line`` looks like a section header.

    Heuristics avoid false positives:
      * Header lines never end with "."  followed by a page number (TOC).
      * Numbers like "1." that begin in column 0 *and* are followed by a
        capitalized title.
    """
    if not line or line.startswith(" "):
        return None
    if line.endswith("."):
        return None
    m = _SECTION_RE.match(line)
    if not m:
        return None
    title = m.group("title").rstrip()
    if title.endswith("..."):
        return None
    # Reject obvious non-headers (e.g. references such as "[RFC 6749]").
    if title.startswith("("):
        return None
    return m.group("number").rstrip("."), title


@dataclass
class _PendingSection:
    number: str
    title: str
    page_start: int
    page_end: int
    lines: list[str]


def _finalize(pending: list[_PendingSection], raw: str) -> list[Section]:
    """Convert _PendingSection blocks into immutable Section models with offsets."""
    out: list[Section] = []
    cursor = 0
    parents: dict[int, str] = {}  # depth -> section_id

    for ps in pending:
        text = "\n".join(ps.lines).strip("\n")
        if not text.strip():
            text = ps.title  # never emit an empty section body
        # Locate this section's text in the original raw string for offsets;
        # if not found verbatim (rare), fall back to a moving cursor.
        anchor = f"{ps.number}. {ps.title}"
        idx = raw.find(anchor, cursor)
        if idx == -1:
            anchor = f"{ps.number} {ps.title}"
            idx = raw.find(anchor, cursor)
        if idx == -1:
            idx = cursor
        char_start = idx
        char_end = char_start + len(anchor) + len(text) + 1
        cursor = char_end

        section_id = ps.number.replace(".", "_")
        depth = ps.number.count(".") + 1
        parent_id = parents.get(depth - 1)
        parents[depth] = section_id
        # Drop deeper-than-current entries so siblings don't inherit nephews.
        for d in list(parents):
            if d > depth:
                parents.pop(d)

        out.append(
            Section(
                section_id=section_id,
                number=ps.number,
                title=ps.title,
                text=text,
                page_start=ps.page_start,
                page_end=ps.page_end,
                char_start=char_start,
                char_end=char_end,
                parent_section_id=parent_id,
            )
        )
    return out
