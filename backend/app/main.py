import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import alerts as alerts_api
from app.api import chaos as chaos_api
from app.api import dashboard as dashboard_api
from app.api import shipments as shipments_api
from app.cache.client import get_all_states, make_client
from app.core.config import settings
from app.db.session import engine
from app.ws.manager import manager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")


async def redis_bridge(app: FastAPI) -> None:
    """Subscribe to ws:broadcast and forward everything to browsers.

    This is the link between the worker process and the WebSocket clients.
    It reconnects on failure rather than dying, so a Redis restart doesn't
    silently leave the dashboard frozen with no error anywhere.
    """
    while True:
        try:
            pubsub = app.state.redis.pubsub()
            await pubsub.subscribe(settings.ws_channel)
            log.info("Subscribed to %s", settings.ws_channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    await manager.broadcast(message["data"])

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Redis bridge dropped — retrying in 3s")
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_client()
    app.state.bridge = asyncio.create_task(redis_bridge(app))
    yield
    app.state.bridge.cancel()
    try:
        await app.state.bridge
    except asyncio.CancelledError:
        pass
    await app.state.redis.aclose()


app = FastAPI(title="LogiPulse Control Tower", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(dashboard_api.router)
app.include_router(shipments_api.router)
app.include_router(alerts_api.router)
app.include_router(chaos_api.router)


@app.get("/health")
async def health():
    """Per-dependency status, so a partial outage is visible as degraded
    rather than as a blank dashboard."""
    deps = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        deps["postgres"] = "up"
    except Exception as exc:
        deps["postgres"] = f"down: {type(exc).__name__}"

    try:
        await app.state.redis.ping()
        deps["redis"] = "up"
    except Exception as exc:
        deps["redis"] = f"down: {type(exc).__name__}"

    overall = "healthy" if all(v == "up" for v in deps.values()) else "degraded"
    return {
        "status": overall,
        "dependencies": deps,
        "websocket_connections": manager.count,
    }


@app.get("/api/shipments/live")
async def live_shipments():
    """Current state of every active shipment, straight from Redis."""
    states = await get_all_states(app.state.redis)
    return {"count": len(states), "shipments": states}


@app.websocket("/ws/shipments")
async def ws_shipments(websocket: WebSocket):
    await manager.connect(websocket)

    # Send a snapshot on connect so a browser that joins mid-stream isn't
    # staring at an empty map until the next event happens to arrive.
    try:
        states = await get_all_states(app.state.redis)
        await websocket.send_json({"type": "SNAPSHOT", "shipments": states})
    except Exception:
        log.exception("Snapshot failed")

    try:
        while True:
            # We don't expect client messages; this keeps the connection
            # open and gives us a clean disconnect signal.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
