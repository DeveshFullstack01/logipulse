"""Shipment simulator.

Loads active shipments from Postgres, then every tick advances each one a
little along its great-circle route and publishes an event to Kafka.

Anomalies (delays, stale updates) are injected randomly so the alert worker
has something to detect. A chaos hook reads Redis each tick, which is what
the Chaos Panel in the UI will drive later.

Run:  python -m simulator.shipment_simulator
Stop: Ctrl+C
"""
import asyncio
import json
import logging
import random
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.kafka.producer import EventProducer
from app.models import Route, Shipment
from app.schemas.events import DelayReason, EventType, ShipmentEvent
from simulator.geo import haversine_km, interpolate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("simulator")

# Probability per tick, per shipment
P_DELAY = 0.010      # a new delay starts
P_STALE = 0.005      # shipment goes quiet for a while
P_RECOVER = 0.100    # a delayed shipment starts moving again

CHAOS_KEY = "sim:chaos"


@dataclass
class SimShipment:
    """In-memory state for one moving shipment."""
    number: str
    origin: str
    destination: str
    o_lat: float
    o_lon: float
    d_lat: float
    d_lon: float
    distance_km: float
    duration_hours: float
    progress: float
    status: str
    expected_delivery: datetime

    delayed: bool = False
    delay_hours: float = 0.0
    delay_reason: DelayReason | None = None
    stale_ticks: int = 0
    departed: bool = False
    speed_kmh: float = field(default=0.0)

    @property
    def target_seconds(self) -> float:
        """Wall-clock seconds for the full journey: 8 min for the shortest
        route, ~30 min for the longest. Keeps every route visible in a demo."""
        span = min(self.duration_hours / 384.0, 1.0)
        return (8 + span * 22) * 60

    @property
    def position(self) -> tuple[float, float]:
        return interpolate(self.o_lat, self.o_lon, self.d_lat, self.d_lon, self.progress)

    @property
    def eta(self) -> datetime:
        return self.expected_delivery + timedelta(hours=self.delay_hours)


def load_shipments() -> list[SimShipment]:
    """Pull undelivered shipments out of Postgres into memory."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Shipment, Route)
            .join(Route, Shipment.route_id == Route.id)
            .where(Shipment.status != "DELIVERED")
        ).all()

        out = []
        for s, r in rows:
            out.append(SimShipment(
                number=s.shipment_number,
                origin=r.origin, destination=r.destination,
                o_lat=r.origin_lat, o_lon=r.origin_lon,
                d_lat=r.dest_lat, d_lon=r.dest_lon,
                distance_km=r.distance_km or haversine_km(
                    r.origin_lat, r.origin_lon, r.dest_lat, r.dest_lon
                ),
                duration_hours=r.expected_duration_hours,
                progress=s.progress or 0.0,
                status=s.status,
                expected_delivery=s.expected_delivery,
                departed=s.status in ("IN_TRANSIT", "DELAYED"),
            ))
        return out
    finally:
        db.close()


async def read_chaos(redis) -> dict:
    """Chaos Panel hook.

    The UI writes a JSON blob here; we read it every tick. Returning {} when
    Redis is unavailable means the simulator keeps running even if the cache
    goes down — a deliberate choice, not an oversight.
    """
    try:
        raw = await redis.get(CHAOS_KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def step(sh: SimShipment, tick_seconds: float, chaos: dict) -> list[ShipmentEvent]:
    """Advance one shipment by one tick. Returns events to publish."""
    events: list[ShipmentEvent] = []

    # --- still quiet? emit nothing (this is what triggers stale alerts) ---
    if sh.stale_ticks > 0:
        sh.stale_ticks -= 1
        return events

    # --- lifecycle: CREATED -> PICKED_UP -> IN_TRANSIT ---
    if sh.status == "CREATED":
        sh.status = "PICKED_UP"
        events.append(ShipmentEvent(
            event_type=EventType.SHIPMENT_PICKED_UP,
            shipment_number=sh.number,
            status=sh.status, progress=sh.progress,
            latitude=sh.o_lat, longitude=sh.o_lon,
        ))
        return events

    if sh.status == "PICKED_UP":
        sh.status = "IN_TRANSIT"
        sh.departed = True
        events.append(ShipmentEvent(
            event_type=EventType.SHIPMENT_DEPARTED,
            shipment_number=sh.number,
            status=sh.status, progress=sh.progress,
            latitude=sh.o_lat, longitude=sh.o_lon,
        ))
        return events

    # --- chaos injection from the UI ---
    ports = chaos.get("congest_ports", [])
    forced_delay = (
        chaos.get("delay_all")
        or sh.number in chaos.get("delay_shipments", [])
        or sh.origin in ports
        or sh.destination in ports
    )
    if chaos.get("freeze_shipments") and sh.number in chaos["freeze_shipments"]:
        sh.stale_ticks = 20
        return events

    # --- random anomalies ---
    if not sh.delayed and (forced_delay or random.random() < P_DELAY):
        sh.delayed = True
        sh.delay_reason = DelayReason(
            chaos.get("delay_reason")
            or random.choices(
                [r.value for r in DelayReason],
                weights=[42, 27, 18, 8, 5],
            )[0]
        )
        sh.delay_hours = round(random.uniform(1.5, 9.0), 1)
        sh.status = "DELAYED"
        lat, lon = sh.position
        events.append(ShipmentEvent(
            event_type=EventType.SHIPMENT_DELAYED,
            shipment_number=sh.number,
            status=sh.status, progress=sh.progress,
            latitude=lat, longitude=lon,
            delay_hours=sh.delay_hours,
            delay_reason=sh.delay_reason,
            estimated_delivery=sh.eta,
        ))
        return events

    if sh.delayed and random.random() < P_RECOVER:
        sh.delayed = False
        sh.status = "IN_TRANSIT"

    if random.random() < P_STALE:
        sh.stale_ticks = random.randint(8, 25)
        return events

    # --- normal movement ---
    # Pacing is chosen for the demo, not for realism. A fixed speed-up factor
    # would make the 4-hour Delhi->Dubai flight finish in 24 seconds while
    # Cochin->Rotterdam took half an hour. Instead every shipment completes in
    # 8-30 minutes of wall clock, with longer routes taking proportionally
    # longer, so there is always something moving on the map.
    fraction = tick_seconds / max(sh.target_seconds, 1.0)
    if sh.delayed:
        fraction *= 0.15  # crawling, not stopped

    sh.progress = min(1.0, sh.progress + fraction)

    # Speed is derived from the *simulated* journey time so the number shown
    # in the UI is plausible for the route, not the accelerated clock.
    sim_hours_per_tick = fraction * sh.duration_hours
    sh.speed_kmh = round(
        (sh.distance_km * fraction) / max(sim_hours_per_tick, 1e-6), 1
    )

    lat, lon = sh.position

    if sh.progress >= 1.0:
        sh.status = "DELIVERED"
        events.append(ShipmentEvent(
            event_type=EventType.SHIPMENT_DELIVERED,
            shipment_number=sh.number,
            status=sh.status, progress=1.0,
            latitude=sh.d_lat, longitude=sh.d_lon,
            delay_hours=sh.delay_hours or None,
            estimated_delivery=sh.eta,
        ))
    else:
        events.append(ShipmentEvent(
            event_type=EventType.SHIPMENT_LOCATION_UPDATED,
            shipment_number=sh.number,
            status=sh.status, progress=round(sh.progress, 4),
            latitude=round(lat, 5), longitude=round(lon, 5),
            speed_kmh=sh.speed_kmh,
            delay_hours=sh.delay_hours or None,
            delay_reason=sh.delay_reason,
            estimated_delivery=sh.eta,
        ))

    return events


async def run() -> None:
    shipments = load_shipments()
    if not shipments:
        log.error("No shipments found. Run 'python seed.py' first.")
        return

    log.info("Loaded %d shipments from Postgres", len(shipments))

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    stopping = asyncio.Event()

    def _stop(*_):
        log.info("Shutting down...")
        stopping.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    tick = settings.simulator_tick_seconds
    published = 0

    async with EventProducer() as producer:
        log.info("Producing to topic '%s' every %.1fs", settings.kafka_topic, tick)
        while not stopping.is_set():
            chaos = await read_chaos(redis)
            batch: list[ShipmentEvent] = []

            for sh in shipments:
                if sh.status == "DELIVERED":
                    continue
                batch.extend(step(sh, tick, chaos))

            for ev in batch:
                await producer.publish(ev)

            published += len(batch)
            active = sum(1 for s in shipments if s.status != "DELIVERED")
            delayed = sum(1 for s in shipments if s.delayed)

            log.info(
                "tick: +%-3d events  |  total %-6d  |  active %-4d  delayed %-3d",
                len(batch), published, active, delayed,
            )

            if active == 0:
                log.info("All shipments delivered. Done.")
                break

            try:
                await asyncio.wait_for(stopping.wait(), timeout=tick)
            except asyncio.TimeoutError:
                pass

    await redis.aclose()
    log.info("Published %d events total", published)


if __name__ == "__main__":
    asyncio.run(run())
