"""Map internal agent/tool events to analyst-friendly pipeline status."""

from __future__ import annotations

from app.assistant.deps import DocumentAgentDeps
from app.assistant.progress import report_progress


def emit_tool_start(deps: DocumentAgentDeps, name: str, detail: str) -> None:
    report_progress(f"tool {name} start {detail}")
    stage, message = _tool_start_status(name, detail)
    deps.emit_status(stage, message)


def emit_agent_start(deps: DocumentAgentDeps, *, model: str, request_limit: int) -> None:
    report_progress(
        f"agent run start model={model} request_limit={request_limit}"
    )
    deps.emit_status("analyzing", "Analyzing your question…")


def emit_agent_done(
    deps: DocumentAgentDeps,
    *,
    requests: int,
    tool_calls: int,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    report_progress(
        "agent run done "
        f"requests={requests} tool_calls={tool_calls} "
        f"input_tokens={input_tokens} output_tokens={output_tokens}"
    )
    deps.emit_status("verifying", "Verifying citations…")


def _tool_start_status(name: str, detail: str) -> tuple[str, str]:
    if name == "search_filings":
        suffix = f" ({detail})" if detail != "no filters" else ""
        return "searching", f"Searching SEC filings…{suffix}"
    if name == "read_surrounding_chunks":
        return "reading", "Reading surrounding context…"
    if name in {"read_chunk", "read_chunks"}:
        return "reading", "Reading source passages…"
    return "reading", "Reading source documents…"
