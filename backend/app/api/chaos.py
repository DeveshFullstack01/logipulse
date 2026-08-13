"""Chaos controls.

Writes a small JSON blob to a Redis key that the simulator reads on every
tick. Nothing here reaches into the simulator process directly — it stays a
separate program that happens to read a shared setting, which is why this
works even though the two run independently.

The point is a demo you can steer: press a button, and the consequences
arrive through the real pipeline a few seconds later.
"""
import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

CHAOS_KEY = "sim:chaos"

router = APIRouter(prefix="/api/chaos", tags=["chaos"])


class ChaosState(BaseModel):
    delay_all: bool = False
    delay_reason: str | None = None
    delay_shipments: list[str] = []
    freeze_shipments: list[str] = []
    congest_ports: list[str] = []


async def _read(request: Request) -> ChaosState:
    raw = await request.app.state.redis.get(CHAOS_KEY)
    return ChaosState(**json.loads(raw)) if raw else ChaosState()


async def _write(request: Request, state: ChaosState) -> ChaosState:
    await request.app.state.redis.set(CHAOS_KEY, state.model_dump_json())
    return state


@router.get("")
async def get_chaos(request: Request) -> ChaosState:
    return await _read(request)


@router.post("/port/{port}")
async def congest_port(port: str, request: Request):
    """Everything routed through this port starts running late."""
    state = await _read(request)
    if port not in state.congest_ports:
        state.congest_ports.append(port)
    state.delay_reason = "PORT_CONGESTION"
    return await _write(request, state)


@router.post("/storm")
async def storm(request: Request):
    """Weather across the whole fleet — the loud one for a demo."""
    state = await _read(request)
    state.delay_all = True
    state.delay_reason = "WEATHER"
    return await _write(request, state)


@router.post("/freeze/{shipment_number}")
async def freeze(shipment_number: str, request: Request):
    """Stop this vessel reporting, so the stale scanner picks it up."""
    state = await _read(request)
    if shipment_number not in state.freeze_shipments:
        state.freeze_shipments.append(shipment_number)
    return await _write(request, state)


@router.post("/delay/{shipment_number}")
async def delay_one(shipment_number: str, request: Request):
    state = await _read(request)
    if shipment_number not in state.delay_shipments:
        state.delay_shipments.append(shipment_number)
    return await _write(request, state)


@router.delete("")
async def clear(request: Request):
    """Calm restored. Shipments recover on their own from here."""
    return await _write(request, ChaosState())
