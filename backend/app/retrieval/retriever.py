"""Hybrid retrieval orchestrator: embed → search → fuse → hydrate."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.database.documents import get_chunks_by_ids, get_surrounding_chunks
from app.database.session import get_session
from app.retrieval.embeddings import embed_query
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keywords import extract_fts_keywords
from app.retrieval.queries import full_text_search, semantic_search
from app.retrieval.types import RankedChunkHit, RetrievedPassage, SearchFilters

from app.database.models import DocumentChunk, SourceDocument


class DocumentRetriever:
    def search(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
        top_k: int | None = None,
        candidate_k: int | None = None,
        include_neighbors: bool = True,
        session: Session | None = None,
    ) -> list[RetrievedPassage]:
        resolved_top_k = top_k if top_k is not None else settings.retrieval_top_k
        resolved_candidate_k = (
            candidate_k if candidate_k is not None else settings.retrieval_candidate_k
        )
        if session is not None:
            return self._search_with_session(
                session,
                query,
                filters=filters,
                top_k=resolved_top_k,
                candidate_k=resolved_candidate_k,
                include_neighbors=include_neighbors,
            )

        with get_session() as owned_session:
            return self._search_with_session(
                owned_session,
                query,
                filters=filters,
                top_k=resolved_top_k,
                candidate_k=resolved_candidate_k,
                include_neighbors=include_neighbors,
            )

    def _search_with_session(
        self,
        session: Session,
        query: str,
        *,
        filters: SearchFilters | None,
        top_k: int,
        candidate_k: int,
        include_neighbors: bool,
    ) -> list[RetrievedPassage]:
        with ThreadPoolExecutor(max_workers=2) as prep:
            embed_future = prep.submit(embed_query, query)
            kw_future = prep.submit(extract_fts_keywords, query, filters=filters)
            query_vec = embed_future.result()
            fts_query = kw_future.result()

        semantic_hits, fts_hits = _dual_search(
            query_vec,
            fts_query,
            candidate_k=candidate_k,
            filters=filters,
        )

        semantic_ids = [hit.chunk_id for hit in semantic_hits]
        fts_ids = [hit.chunk_id for hit in fts_hits]
        fused = reciprocal_rank_fusion(
            [semantic_ids, fts_ids],
            k=settings.retrieval_rrf_k,
        )[:top_k]

        if not fused:
            return []

        fused_ids = [chunk_id for chunk_id, _ in fused]
        fusion_scores = {chunk_id: score for chunk_id, score in fused}
        chunks_by_id = get_chunks_by_ids(session, fused_ids)

        passages: list[RetrievedPassage] = []
        seen_neighbor_ids: set[UUID] = set(fused_ids)

        for chunk_id in fused_ids:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None or chunk.document is None:
                continue

            neighbors: list[RetrievedPassage] = []
            if include_neighbors:
                for neighbor_chunk in get_surrounding_chunks(
                    session,
                    chunk_id,
                    settings.retrieval_neighbor_radius,
                ):
                    if neighbor_chunk.id in seen_neighbor_ids:
                        continue
                    if neighbor_chunk.document is None:
                        continue
                    seen_neighbor_ids.add(neighbor_chunk.id)
                    neighbors.append(
                        _passage_from_chunk(
                            neighbor_chunk,
                            neighbor_chunk.document,
                            fusion_score=0.0,
                        )
                    )

            passages.append(
                _passage_from_chunk(
                    chunk,
                    chunk.document,
                    fusion_score=fusion_scores[chunk_id],
                    neighbors=neighbors,
                )
            )

        return passages


def _dual_search(
    query_vec: list[float],
    fts_query: str,
    *,
    candidate_k: int,
    filters: SearchFilters | None,
) -> tuple[list[RankedChunkHit], list[RankedChunkHit]]:
    """Run semantic and full-text search in parallel (separate DB sessions)."""

    def semantic() -> list[RankedChunkHit]:
        with get_session() as search_session:
            return semantic_search(
                search_session,
                query_vec,
                limit=candidate_k,
                filters=filters,
            )

    def fts() -> list[RankedChunkHit]:
        with get_session() as search_session:
            return full_text_search(
                search_session,
                fts_query,
                limit=candidate_k,
                filters=filters,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        semantic_future = executor.submit(semantic)
        fts_future = executor.submit(fts)
        return semantic_future.result(), fts_future.result()


def _passage_from_chunk(
    chunk: DocumentChunk,
    document: SourceDocument,
    *,
    fusion_score: float,
    neighbors: list[RetrievedPassage] | None = None,
) -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        page=chunk.page,
        section=chunk.section,
        fusion_score=fusion_score,
        ticker=document.ticker,
        company_name=document.company_name,
        form=document.form,
        filing_date=document.filing_date,
        fiscal_year=document.fiscal_year,
        accession_number=document.accession_number,
        neighbors=neighbors or [],
    )
