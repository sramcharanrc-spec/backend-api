import asyncio
import inspect
import logging
import time
from threading import RLock
from typing import Any, Dict

try:
    from cachetools import TTLCache

except ModuleNotFoundError:

    class TTLCache(dict):

        def __init__(
            self,
            maxsize:int,
            ttl:int
        ):
            super().__init__()

            self.maxsize=maxsize
            self.ttl=ttl
            self._expires={}

        def _expire(self):

            now=time.monotonic()

            expired=[

                key

                for key,expires_at
                in self._expires.items()

                if expires_at<=now
            ]

            for key in expired:

                self.pop(
                    key,
                    None
                )

        def __contains__(
            self,
            key
        ):

            self._expire()

            return super().__contains__(
                key
            )

        def __setitem__(
            self,
            key,
            value
        ):

            self._expire()

            if (
                len(self)>=self.maxsize
                and
                key not in self
            ):

                oldest=min(
                    self._expires,
                    key=self._expires.get
                )

                self.pop(
                    oldest,
                    None
                )

            self._expires[key]=(
                time.monotonic()
                +self.ttl
            )

            super().__setitem__(
                key,
                value
            )


processed_events=TTLCache(
    maxsize=10000,
    ttl=300
)

_lock=RLock()

def should_emit(
    event:Dict[str,Any]
)->bool:

    key=event_key(
        event
    )

    if not key:
        return False

    with _lock:

        if key in processed_events:
            return False

        processed_events[
            key
        ]=True

    return True

def normalize_text(
    value:Any
)->str:

    return str(
        value or ""
    ).strip()


logger=logging.getLogger(__name__)

def event_key(
    event:Dict[str,Any]
)->str:

    if not isinstance(event,dict):
        return ""

    claim_id=normalize_text(
        event.get("claim_id")
        or event.get("claimId")
    )

    stage=normalize_text(
        event.get("stage")
        or event.get("agent")
        or event.get("step")
    ).lower()

    status=normalize_text(
        event.get("status")
    ).upper()

    timestamp=normalize_text(
    event.get(
        "timestamp"
        )
    )

    if not timestamp:

        timestamp="default"

    if not claim_id or not stage or not status:
        return ""

    return (
        f"{claim_id}:"
        f"{stage}:"
        f"{status}:"
        f"{timestamp}"
    )

def clear_processed_events():

    with _lock:

        processed_events.clear()

async def emit_once_async(
    socket_manager,
    event:Dict[str,Any]
):

    if not should_emit(
        event
    ):
        return False

    try:

        result=socket_manager.broadcast(
            event
        )

        if inspect.isawaitable(
            result
        ):
            await result

        return True

    except Exception:

        logger.exception(
            "WebSocket emit error"
        )

        return False

def emit_once(
    socket_manager,
    event:Dict[str,Any]
):

    try:

        loop=asyncio.get_running_loop()

        loop.create_task(

            emit_once_async(
                socket_manager,
                event
            )
        )

        return True

    except RuntimeError:

        return asyncio.run(

            emit_once_async(
                socket_manager,
                event
            )
        )