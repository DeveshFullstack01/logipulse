from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()


app = FastAPI(title="LogiPulse Control Tower", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Per-dependency status. This is what you point at when an interviewer
    asks 'what happens if Redis goes down?' -- the app degrades, it doesn't die."""
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
    return {"status": overall, "dependencies": deps}
