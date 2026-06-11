import time
import traceback
from datetime import datetime
from typing import Any, Awaitable, Callable

from app.websocket.manager import manager


STATUS_ICONS = {
    "START": "🚀",
    "INFO": "📌",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "PROCESS": "⚙️",
    "AI": "🧠",
    "DB": "💾",
    "QUEUE": "📦",
    "ROUTE": "🔀",
    "STOP": "🛑",
}

BANNER_WIDTH = 47


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _agent_label(agent: str | None) -> str:
    return str(agent or "PIPELINE").upper()


def _step_key(agent: str | None) -> str:
    value = _agent_label(agent).lower()
    aliases = {
        "acknowledgment": "clearinghouse",
        "denial": "denial_ai",
        "denial_ai": "denial_ai",
        "feedback_loop": "learning",
    }
    return aliases.get(value, value)


def _get_claim(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    claim = state.get("claim")
    return claim if isinstance(claim, dict) else {}


def get_trace_ids(state: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    claim = _get_claim(state)
    case = state.get("case") if isinstance(state, dict) else {}
    if not isinstance(case, dict):
        case = {}

    claim_id = claim.get("claim_id") or (state or {}).get("claim_id")
    submission_id = claim.get("submission_id") or (state or {}).get("submission_id")
    case_id = case.get("case_id") or claim.get("case_id") or (state or {}).get("case_id")
    return claim_id, submission_id, case_id


def pipeline_log(
    agent,
    message,
    claim_id=None,
    submission_id=None,
    case_id=None,
    status="INFO",
) -> None:
    icon = STATUS_ICONS.get(str(status).upper(), STATUS_ICONS["INFO"])
    lines = [
        f"[{_timestamp()}]",
        f"{icon} [{_agent_label(agent)}]",
    ]
    if claim_id:
        lines.append(f"[CLAIM: {claim_id}]")
    if submission_id:
        lines.append(f"[SUBMISSION: {submission_id}]")
    if case_id:
        lines.append(f"[CASE: {case_id}]")
    lines.append(str(message))
    print("\n".join(lines), flush=True)


def pipeline_banner(message: str, icon: str) -> None:
    border = "═" * BANNER_WIDTH
    print(f"\n{border}\n{icon} {message}\n{border}\n", flush=True)


async def emit_pipeline_event(
    agent,
    status,
    message,
    claim_id=None,
    submission_id=None,
    case_id=None,
    metadata=None,
) -> None:
    payload = {
        "type": "pipeline_event",
        "agent": _agent_label(agent),
        "step": _step_key(agent),
        "status": str(status).upper(),
        "message": message,
        "claim_id": claim_id,
        "submission_id": submission_id,
        "case_id": case_id,
        "timestamp": _timestamp(),
        "metadata": metadata or {},
    }
    await manager.broadcast(payload)
    await manager.send_agent_update(
        _step_key(agent),
        status,
        {
            "claim_id": claim_id,
            "agent": _agent_label(agent),
            "stage": _step_key(agent),
            "status": status,
            "message": message,
            "reasoning": (metadata or {}).get("reasoning") or message,
            "input": (metadata or {}).get("input"),
            "output": (metadata or {}).get("output"),
            "input_count": (metadata or {}).get("input_count"),
            "output_count": (metadata or {}).get("output_count"),
            "confidence": (metadata or {}).get("confidence") or (metadata or {}).get("ai_confidence"),
            "warnings": (metadata or {}).get("warnings"),
            "metrics": (metadata or {}).get("metrics") or {
                "latency": (metadata or {}).get("execution_time_seconds"),
                "tokens": (metadata or {}).get("tokens"),
            },
            "processing_time": (
                (metadata or {}).get("execution_time_seconds") * 1000
                if isinstance((metadata or {}).get("execution_time_seconds"), (int, float))
                else (metadata or {}).get("processing_time")
            ),
            "ai_summary": (metadata or {}).get("ai_summary") or message,
            "next_agent": (metadata or {}).get("next_agent"),
            "event_history": (metadata or {}).get("event_history"),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


async def log_and_emit(
    agent,
    message,
    state=None,
    status="INFO",
    metadata=None,
) -> None:
    claim_id, submission_id, case_id = get_trace_ids(state)
    claim = _get_claim(state)
    event_metadata = {**(metadata or {})}
    if claim.get("claim_type") and "claim_type" not in event_metadata:
        event_metadata["claim_type"] = claim.get("claim_type")
    pipeline_log(agent, message, claim_id, submission_id, case_id, status)
    await emit_pipeline_event(
        agent,
        status,
        message,
        claim_id=claim_id,
        submission_id=submission_id,
        case_id=case_id,
        metadata=event_metadata,
    )


def _merge_agent_result(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    if "pipeline" in result and isinstance(result["pipeline"], dict) and "steps" in result["pipeline"]:
        state.setdefault("pipeline", {"steps": {}})
        state["pipeline"].setdefault("steps", {})
        state["pipeline"]["steps"].update(result["pipeline"]["steps"])

    for key, value in result.items():
        if key != "pipeline":
            state[key] = value

    return state


def create_logged_node(agent_name, agent_instance):
    async def node(state):
        if not isinstance(state, dict):
            raise ValueError("state must be a dictionary")

        claim = state.get("claim")
        if claim is None and hasattr(agent_instance, "run"):
            raise ValueError("claim missing in state")

        start = time.perf_counter()
        await log_and_emit(
            agent_name,
            f"{_agent_label(agent_name).title()} started",
            state,
            status="START",
        )

        try:
            if hasattr(agent_instance, "run"):
                result = await agent_instance.run(claim) or {}
                state = _merge_agent_result(state, result)
            else:
                result = await agent_instance(state)
                state = result if isinstance(result, dict) else state

            duration = time.perf_counter() - start
            state.setdefault("metrics", {})
            state["metrics"][f"{agent_name}_duration_seconds"] = round(duration, 3)

            await log_and_emit(
                agent_name,
                f"Agent completed successfully ({duration:.2f}s)",
                state,
                status="SUCCESS",
                metadata={"execution_time_seconds": round(duration, 3)},
            )
            return state

        except Exception as error:
            duration = time.perf_counter() - start
            stack = traceback.format_exc()
            await log_and_emit(
                agent_name,
                f"Agent failed after {duration:.2f}s: {error}\n{stack}",
                state,
                status="ERROR",
                metadata={
                    "execution_time_seconds": round(duration, 3),
                    "error": str(error),
                    "traceback": stack,
                },
            )
            raise

    return node
