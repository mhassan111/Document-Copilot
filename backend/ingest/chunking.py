"""Docling-based chunking for SEC HTML filings."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
    HierarchicalChunker,
)
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.transforms.serializer.markdown import (
    MarkdownParams,
    MarkdownTableSerializer,
)
from ingest.sec_tables import ExtractedTable, TableRow, extract_sec_tables

CHUNK_MAX_TOKENS = 512
DOWNLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "downloads"
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "markdown" / "manifest.json"

_ITEM_SECTION_RE = re.compile(r"\bItem\s+[\dA-Z.]+\b", re.IGNORECASE)


class PatchedOpenAITokenizer(OpenAITokenizer):
    """Allow tiktoken special tokens that appear in SEC filing text."""

    def count_tokens(self, text: str) -> int:
        return len(
            self.tokenizer.encode(
                text=text,
                allowed_special=set(),
                disallowed_special=(),
            )
        )


class MarkdownTableSerializerProvider(ChunkingSerializerProvider):
    """Serialize tables as Markdown for 10-K financial tables."""

    def get_serializer(self, doc: Any) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
            params=MarkdownParams(compact_tables=True),
        )


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_index: int
    text: str
    page: str | None
    section: str | None
    token_count: int
    chunk_metadata: dict[str, Any]


def load_manifest_html_paths() -> dict[str, str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    paths: dict[str, str] = {}
    for filing in manifest.get("filings", []):
        accession = filing["accession_number"]
        html_path = filing.get("html_local_path")
        if not html_path:
            html_path = str(Path(filing["local_path"]).with_suffix(".htm"))
        paths[accession] = html_path
    return paths


def html_path_for_accession(accession_number: str) -> Path:
    paths = load_manifest_html_paths()
    if accession_number not in paths:
        raise KeyError(f"Accession {accession_number} not found in {MANIFEST_PATH}")
    html_path = DOWNLOADS_DIR / paths[accession_number]
    if not html_path.is_file():
        raise FileNotFoundError(f"Missing HTML file: {html_path}")
    return html_path


def build_tokenizer(max_tokens: int = CHUNK_MAX_TOKENS) -> PatchedOpenAITokenizer:
    return PatchedOpenAITokenizer(
        tokenizer=tiktoken.get_encoding("cl100k_base"),
        max_tokens=max_tokens,
    )


def build_hybrid_chunker(
    max_tokens: int = CHUNK_MAX_TOKENS,
) -> HybridChunker:
    # HybridChunker applies token-aware splits on top of HierarchicalChunker output.
    return HybridChunker(
        tokenizer=build_tokenizer(max_tokens=max_tokens),
        merge_peers=True,
        repeat_table_header=True,
        serializer_provider=MarkdownTableSerializerProvider(),
    )


def build_hierarchical_chunker() -> HierarchicalChunker:
    return HierarchicalChunker(
        serializer_provider=MarkdownTableSerializerProvider(),
    )


def convert_html_to_document(html_path: Path) -> Any:
    return DocumentConverter().convert(html_path).document


def _page_from_chunk_meta(meta: Any) -> str | None:
    origin = getattr(meta, "origin", None)
    if origin is not None:
        page_no = getattr(origin, "page_no", None)
        if page_no is not None:
            return str(page_no)

    for item in getattr(meta, "doc_items", []):
        prov = getattr(item, "prov", None) or []
        for entry in prov:
            page_no = getattr(entry, "page_no", None)
            if page_no is not None:
                return str(page_no)
    return None


def _section_from_chunk(meta: Any, text: str) -> str | None:
    headings = getattr(meta, "headings", None) or []
    if headings:
        return " > ".join(headings)

    match = _ITEM_SECTION_RE.search(text)
    if match:
        return match.group(0)
    return None


def map_chunk_record(
    *,
    chunk_index: int,
    chunk: Any,
    chunker: HybridChunker,
    filing_metadata: dict[str, Any],
) -> ChunkRecord:
    contextualized = chunker.contextualize(chunk=chunk)
    meta = chunk.meta
    tokenizer = chunker.tokenizer

    return ChunkRecord(
        chunk_index=chunk_index,
        text=contextualized,
        page=_page_from_chunk_meta(meta),
        section=_section_from_chunk(meta, contextualized),
        token_count=tokenizer.count_tokens(contextualized),
        chunk_metadata={
            **_base_chunk_metadata(filing_metadata),
            "chunk_kind": "narrative",
            "raw_text": chunk.text,
            "docling_meta": meta.export_json_dict(),
        },
    )


def chunk_document(
    html_path: Path,
    filing_metadata: dict[str, Any],
    *,
    max_chunks: int | None = None,
) -> list[ChunkRecord]:
    html = html_path.read_text(encoding="utf-8")
    doc = convert_html_to_document(html_path)
    chunker = build_hybrid_chunker()
    tables = extract_sec_tables(html)
    used_table_indexes: set[int] = set()
    records: list[ChunkRecord] = []

    for index, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        if max_chunks is not None and index >= max_chunks:
            break
        if _chunk_contains_table(chunk):
            table = _matching_table_for_chunk(
                chunker.contextualize(chunk=chunk),
                tables,
                used_table_indexes,
            )
            narrative_text = _narrative_text_without_tables(
                chunker.contextualize(chunk=chunk)
            )
            if narrative_text:
                records.append(
                    ChunkRecord(
                        chunk_index=len(records),
                        text=narrative_text,
                        page=_page_from_chunk_meta(chunk.meta),
                        section=_section_from_chunk(chunk.meta, narrative_text),
                        token_count=chunker.tokenizer.count_tokens(narrative_text),
                        chunk_metadata={
                            **_base_chunk_metadata(filing_metadata),
                            "chunk_kind": "narrative",
                            "raw_text": narrative_text,
                            "docling_meta": chunk.meta.export_json_dict(),
                        },
                    )
                )
            if table is not None:
                _append_table_row_records(
                    records=records,
                    table=table,
                    chunker=chunker,
                    filing_metadata=filing_metadata,
                )
                used_table_indexes.add(table.table_index)
                continue
            records.append(
                map_chunk_record(
                    chunk_index=len(records),
                    chunk=chunk,
                    chunker=chunker,
                    filing_metadata=filing_metadata,
                )
            )
            continue
        records.append(
            map_chunk_record(
                chunk_index=len(records),
                chunk=chunk,
                chunker=chunker,
                filing_metadata=filing_metadata,
            )
        )

    if max_chunks is None:
        for table in tables:
            if table.table_index in used_table_indexes:
                continue
            _append_table_row_records(
                records=records,
                table=table,
                chunker=chunker,
                filing_metadata=filing_metadata,
            )

    return records


def _append_table_row_records(
    *,
    records: list[ChunkRecord],
    table: ExtractedTable,
    chunker: HybridChunker,
    filing_metadata: dict[str, Any],
) -> None:
    for row in table.rows:
        text = _table_row_chunk_text(table, row)
        records.append(
            ChunkRecord(
                chunk_index=len(records),
                text=text,
                page=None,
                section=table.title,
                token_count=chunker.tokenizer.count_tokens(text),
                chunk_metadata={
                    **_base_chunk_metadata(filing_metadata),
                    "chunk_kind": "table_row",
                    "table_index": table.table_index,
                    "table_title": table.title,
                    "row_label": row.label,
                    "raw_text": text,
                    "table": table.to_dict(),
                },
            )
        )


def _base_chunk_metadata(filing_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": filing_metadata.get("ticker"),
        "cik": filing_metadata.get("cik"),
        "company_name": filing_metadata.get("company_name"),
        "form": filing_metadata.get("form"),
        "filing_date": filing_metadata.get("filing_date"),
        "report_date": filing_metadata.get("report_date"),
        "fiscal_year": filing_metadata.get("fiscal_year"),
        "accession_number": filing_metadata.get("accession_number"),
        "primary_document": filing_metadata.get("primary_document"),
        "source_url": filing_metadata.get("source_url"),
    }


def _chunk_contains_table(chunk: Any) -> bool:
    for item in getattr(chunk.meta, "doc_items", []) or []:
        label = str(getattr(item, "label", "")).lower()
        if "table" in label:
            return True
    return False


def _matching_table_for_chunk(
    chunk_text: str,
    tables: list[ExtractedTable],
    used_table_indexes: set[int],
) -> ExtractedTable | None:
    for table in tables:
        if table.table_index in used_table_indexes:
            continue
        if _table_matches_chunk(chunk_text, table):
            return table
    return None


def _table_matches_chunk(chunk_text: str, table: ExtractedTable) -> bool:
    if not table.rows:
        return False
    first_row = table.rows[0]
    if first_row.label and first_row.label in chunk_text:
        return True
    return any(cell.text.strip("$") in chunk_text for cell in first_row.cells if cell.text)


def _narrative_text_without_tables(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _table_row_chunk_text(table: ExtractedTable, row: TableRow) -> str:
    title = table.title or f"Table {table.table_index + 1}"
    lines = [title]
    if table.units:
        lines.append(f"Units: {table.units}")

    row_markdown = _markdown_for_row(table, row)
    lines.append(row_markdown)
    if table.footnotes:
        lines.extend(table.footnotes)
    return "\n".join(lines)


def _markdown_for_row(table: ExtractedTable, row: TableRow) -> str:
    header = "| " + " | ".join(column.label for column in table.columns) + " |"
    separator = "| " + " | ".join("---" for _ in table.columns) + " |"
    body = "| " + " | ".join([row.label, *[cell.text for cell in row.cells]]) + " |"
    return "\n".join([header, separator, body])


def chunk_document_hierarchical(html_path: Path) -> list[str]:
    """Layout-only chunks from HierarchicalChunker (used in tests / inspection)."""
    doc = convert_html_to_document(html_path)
    chunker = build_hierarchical_chunker()
    return [chunk.text for chunk in chunker.chunk(dl_doc=doc)]


def iter_all_html_paths() -> Iterator[tuple[str, Path]]:
    for accession, relative_path in load_manifest_html_paths().items():
        yield accession, DOWNLOADS_DIR / relative_path
