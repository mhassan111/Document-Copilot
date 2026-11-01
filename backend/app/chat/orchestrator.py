"""Coordinates one chat turn: agent → validate → stream → persist."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from supabase import AsyncClient

from app.assistant.agent import run_document_agent
from app.assistant.deps import DocumentAgentDeps, TurnRegistry
from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat.messages import text_from_parts
from app.chat.streaming import (
    stream_grounded_turn_and_persist,
    stream_error,
    stream_status,
)
from app.grounding.validator import GroundingValidator, prune_unreferenced_citations
from app.retrieval.retriever import DocumentRetriever
from app.schemas.chat import UIMessage

MAX_VALIDATION_ATTEMPTS = 2


async def _yield_status_updates(
    status_queue: asyncio.Queue[tuple[str, str]],
    agent_task: asyncio.Task[GroundedAnswer],
) -> AsyncIterator[str]:
    while not agent_task.done():
        try:
            stage, message = await asyncio.wait_for(status_queue.get(), timeout=0.3)
        except TimeoutError:
            continue
        async for event in stream_status(stage, message):
            yield event

    while not status_queue.empty():
        stage, message = status_queue.get_nowait()
        async for event in stream_status(stage, message):
            yield event


async def run_turn(
    *,
    client: AsyncClient,
    thread_id: uuid.UUID,
    user: CurrentUser,
    user_message: UIMessage,
    thread_title: str,
    retriever: DocumentRetriever,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    query = text_from_parts(user_message.parts).strip()
    if not query:
        async for event in stream_error("User message is empty."):
            yield event
        return

    async for event in stream_status("analyzing", "Analyzing your question…"):
        yield event

    grounded: GroundedAnswer | None = None
    validation = None
    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        registry = TurnRegistry()
        status_queue = asyncio.Queue()

        def on_status(stage: str, message: str) -> None:
            loop.call_soon_threadsafe(status_queue.put_nowait, (stage, message))

        deps = DocumentAgentDeps(
            retriever=retriever,
            registry=registry,
            thread_id=thread_id,
            user_id=user.id,
            on_status=on_status,
        )
        agent_task = asyncio.create_task(
            asyncio.to_thread(run_document_agent, query, deps)
        )

        async for event in _yield_status_updates(status_queue, agent_task):
            yield event

        try:
            grounded = await agent_task
        except Exception as exc:
            async for event in stream_error(f"Assistant run failed: {exc}"):
                yield event
            return

        async for event in stream_status("verifying", "Verifying citations…"):
            yield event

        grounded = prune_unreferenced_citations(grounded)
        validation = await GroundingValidator().validate(grounded, registry)
        if validation.ok or attempt == MAX_VALIDATION_ATTEMPTS:
            break

        async for event in stream_status(
            "retrying",
            "Could not fully verify citations; retrying with stricter grounding…",
        ):
            yield event

    if grounded is None or validation is None:
        async for event in stream_error("Assistant run failed before producing an answer."):
            yield event
        return

    if validation.ok:
        async for event in stream_status("streaming", "Preparing answer…"):
            yield event

    async for event in stream_grounded_turn_and_persist(
        client=client,
        thread_id=thread_id,
        user_message=user_message,
        thread_title=thread_title,
        answer=grounded,
        registry=registry,
        validation=validation,
    ):
        yield event
