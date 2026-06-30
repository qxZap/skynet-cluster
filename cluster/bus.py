"""In-process async pub/sub so SSE subscribers get events without polling.

ponytail: asyncio fan-out to per-subscriber queues. Single-process only —
when the cluster goes multi-process, back this with Redis Streams / NATS
(the publish() call site stays the same).
"""
import asyncio

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue):
    _subscribers.discard(q)


def publish(event: dict):
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # ponytail: slow subscriber drops events, not the cluster
