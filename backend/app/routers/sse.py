"""SSE (Server-Sent Events) router for real-time client updates.
Uses Redis pub/sub in production for multi-worker support.
Falls back to in-memory queues in development.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse

from app.auth import get_current_active_user
from app.models import User
from app.redis_client import register_sse_client, unregister_sse_client, subscribe_sse

router = APIRouter(prefix="/api/sse", tags=["SSE"])
logger = logging.getLogger(__name__)


@router.get("")
async def sse_stream(
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """SSE stream endpoint. Client connects and receives real-time events.
    Uses Redis pub/sub in production, in-memory queue as fallback.
    """
    uid = current_user.id

    # In-memory queue for fallback
    q: asyncio.Queue = asyncio.Queue()
    register_sse_client(uid, q)

    # Redis subscription cancel callback
    redis_events: asyncio.Queue = asyncio.Queue()
    cancel_redis = await subscribe_sse(uid, lambda etype, data: redis_events.put_nowait((etype, data)))

    async def event_generator():
        # Send initial balance
        yield f"event: balance\ndata: {json.dumps({'balance': float(current_user.balance or 0)})}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break

                done = False
                # Check Redis events first (no wait)
                try:
                    etype, data = redis_events.get_nowait()
                    yield f"event: {etype}\ndata: {json.dumps(data)}\n\n"
                    done = True
                except asyncio.QueueEmpty:
                    pass

                # Check in-memory queue (no wait)
                if not done:
                    try:
                        event = q.get_nowait()
                        yield f"event: {event['event']}\ndata: {event['data']}\n\n"
                        done = True
                    except asyncio.QueueEmpty:
                        pass

                if not done:
                    # Wait on BOTH queues at once — previously only the in-memory
                    # queue was awaited, so Redis-delivered events (the multi-worker
                    # production path) were delayed up to 15s.
                    q_task = asyncio.ensure_future(q.get())
                    r_task = asyncio.ensure_future(redis_events.get())
                    try:
                        finished, pending = await asyncio.wait(
                            {q_task, r_task},
                            timeout=15.0,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for t in pending:
                            t.cancel()
                        if not finished:
                            yield ": keepalive\n\n"
                        else:
                            for t in finished:
                                if t is q_task:
                                    event = t.result()
                                    yield f"event: {event['event']}\ndata: {event['data']}\n\n"
                                else:
                                    etype, data = t.result()
                                    yield f"event: {etype}\ndata: {json.dumps(data)}\n\n"
                    finally:
                        # Ensure cancelled get() tasks are awaited so no item is
                        # silently lost and no pending-task warning is emitted.
                        for t in (q_task, r_task):
                            if t.cancelled():
                                continue
                            if t.done() and not t.exception() and t not in finished:
                                # A value was dequeued after selection; re-queue it.
                                try:
                                    if t is q_task:
                                        q.put_nowait(t.result())
                                    else:
                                        redis_events.put_nowait(t.result())
                                except Exception:
                                    pass
        except asyncio.CancelledError:
            pass
        finally:
            cancel_redis()
            unregister_sse_client(uid)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
