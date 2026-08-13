"""Redis access.

Deliberately named `cache` rather than `redis` so that `import redis`
inside these modules can never accidentally resolve to the package itself.

Key layout:
  shipment:{number}   JSON blob of that shipment's current state
  shipments:active    SET of shipment numbers not yet delivered
  ws:broadcast        pub/sub channel, worker -> API -> browsers
"""
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

SHIPMENT_KEY = "shipment:{}"
ACTIVE_SET = "shipments:active"


def make_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def set_shipment_state(r: aioredis.Redis, number: str, state: dict[str, Any]) -> None:
    pipe = r.pipeline()
    pipe.set(SHIPMENT_KEY.format(number), json.dumps(state, default=str))
    if state.get("status") == "DELIVERED":
        pipe.srem(ACTIVE_SET, number)
    else:
        pipe.sadd(ACTIVE_SET, number)
    await pipe.execute()


async def get_shipment_state(r: aioredis.Redis, number: str) -> dict | None:
    raw = await r.get(SHIPMENT_KEY.format(number))
    return json.loads(raw) if raw else None


async def get_all_states(r: aioredis.Redis) -> list[dict]:
    """Read every active shipment in ONE round trip.

    This is the whole reason Redis is in the stack: the dashboard asks for
    the current position of every shipment on every poll, and reconstructing
    that from the Postgres event log each time would be absurd.
    """
    numbers = await r.smembers(ACTIVE_SET)
    if not numbers:
        return []
    keys = [SHIPMENT_KEY.format(n) for n in numbers]
    values = await r.mget(keys)
    return [json.loads(v) for v in values if v]


async def publish_ws(r: aioredis.Redis, payload: dict) -> None:
    """Push a message toward every connected browser.

    The worker is a separate OS process from the API, so it cannot touch
    FastAPI's WebSocket objects directly. It publishes here instead; each
    API instance subscribes and fans out to its own clients. This is also
    what makes running several API replicas work without extra plumbing.
    """
    await r.publish(settings.ws_channel, json.dumps(payload, default=str))
