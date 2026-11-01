"""PydanticAI document agent definition."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.assistant.status import emit_agent_done, emit_agent_start
from app.assistant.tools import (
    read_chunk,
    read_chunks,
    read_surrounding_chunks,
    search_filings,
)
from app.config import settings

_INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")
INSTRUCTIONS = _INSTRUCTIONS_PATH.read_text(encoding="utf-8")

_document_agent: Agent[DocumentAgentDeps, GroundedAnswer] | None = None


def get_document_agent() -> Agent[DocumentAgentDeps, GroundedAnswer]:
    global _document_agent
    if _document_agent is None:
        model = OpenAIChatModel(
            settings.openai_chat_model,
            provider=OpenAIProvider(api_key=settings.openai_api_key),
        )
        _document_agent = Agent(
            model,
            deps_type=DocumentAgentDeps,
            output_type=GroundedAnswer,
            instructions=INSTRUCTIONS,
            tools=[search_filings, read_chunks, read_chunk, read_surrounding_chunks],
        )
    return _document_agent


def run_document_agent(query: str, deps: DocumentAgentDeps) -> GroundedAnswer:
    emit_agent_start(
        deps,
        model=settings.openai_chat_model,
        request_limit=settings.openai_agent_request_limit,
    )
    result = get_document_agent().run_sync(
        query,
        deps=deps,
        usage_limits=UsageLimits(request_limit=settings.openai_agent_request_limit),
    )
    usage = result.usage
    emit_agent_done(
        deps,
        requests=usage.requests or 0,
        tool_calls=usage.tool_calls or 0,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
    return result.output
