"""OpenAI embedding generation for document chunks."""

from __future__ import annotations

from openai import OpenAI

from app.config import settings

EMBED_BATCH_SIZE = 100


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(texts: list[str], *, batch_size: int = EMBED_BATCH_SIZE) -> list[list[float]]:
    if not texts:
        return []

    expected_dims = settings.openai_embedding_dimensions
    vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = _client().embeddings.create(
            input=batch,
            model=settings.openai_embedding_model,
            dimensions=expected_dims,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        for item in ordered:
            embedding = item.embedding
            if len(embedding) != expected_dims:
                raise ValueError(
                    f"Expected embedding dimension {expected_dims}, got {len(embedding)}"
                )
            vectors.append(embedding)

    return vectors
