from typing import Dict, Any

from app.utils.event_deduplicator import should_emit

PIPELINE_PROGRESS={

    "extraction":15,
    "eligibility":30,
    "validation":45,
    "compliance":60,
    "submission":80,
    "clearinghouse":100

}

def normalize_event(
    event:Dict[str,Any]
):

    stage=(
        event.get("stage")
        or
        event.get("agent")
        or
        ""
    ).strip().lower()

    status=(
        event.get("status")
        or
        ""
    ).strip().upper()

    event["stage"]=stage
    event["agent"]=stage
    event["status"]=status

    return event


def assign_progress(event):

    progress=event.get(
        "progress",
        0
    )

    if not progress:

        event["progress"]=(
            PIPELINE_PROGRESS.get(
                event["stage"],
                0
            )
        )

    return event


def emit_once(event):
    return should_emit(event)
