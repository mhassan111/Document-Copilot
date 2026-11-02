"""Embedding generation for document chunks (rate-limit aware)."""

from __future__ import annotations

import time

from openai import OpenAI, RateLimitError

from app.config import settings

EMBED_BATCH_SIZE = 20  # ~6-13k tokens per request
TOKENS_PER_MINUTE = 28_000  # stay under the 30k free-tier limit
MAX_RETRIES = 8


def _client() -> OpenAI:
    return OpenAI(
        base_url=settings.gemini_base_url,
        api_key=settings.gemini_api_key,
    )


def _estimate_tokens(texts: list[str]) -> int:
    return sum(len(t) for t in texts) // 3  # conservative chars->tokens


def _embed_batch(batch: list[str], dims: int):
    delay = 40.0
    for attempt in range(MAX_RETRIES):
        try:
            return _client().embeddings.create(
                input=batch,
                model=settings.gemini_embedding_model,
                dimensions=dims,
            )
        except RateLimitError:
            if attempt == MAX_RETRIES - 1:
                raise
            print(f"  429 rate limited, sleeping {delay:.0f}s...", flush=True)
            time.sleep(delay)
            delay = min(delay * 1.5, 120)


def embed_texts(texts: list[str], *, batch_size: int = EMBED_BATCH_SIZE) -> list[list[float]]:
    if not texts:
        return []

    dims = settings.gemini_embedding_dimensions
    vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start: start + batch_size]
        began = time.monotonic()
        response = _embed_batch(batch, dims)

        if len(response.data) != len(batch):
            raise ValueError(
                f"Expected {len(batch)} embeddings, got {len(response.data)}"
            )
        for item in response.data:
            if len(item.embedding) != dims:
                raise ValueError(f"Expected {dims} dims, got {len(item.embedding)}")
            vectors.append(item.embedding)

        # Pace so tokens/minute stays under the limit.
        min_seconds = _estimate_tokens(batch) / TOKENS_PER_MINUTE * 60
        elapsed = time.monotonic() - began
        if elapsed < min_seconds:
            time.sleep(min_seconds - elapsed)

    return vectors
