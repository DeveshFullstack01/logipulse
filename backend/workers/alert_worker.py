"""Alert worker.

A SECOND consumer group on the same `shipment-events` topic. It has its own
offsets and knows nothing about the state worker — both read every message
independently. That is the entire reason Kafka is in this stack rather than
a queue: a queue would hand each message to exactly one consumer.

Detects two conditions:
  DELAY  — an event reports a delay at or past the configured threshold
  STALE  — a shipment has stopped reporting its position

Runs as its own process:  python -m workers.alert_worker
"""
import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone

from aiokafka import AIOKafkaConsumer
from sqlalchemy import select, update

from app.cache.client import get_all_states, make_client, publish_ws
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Alert
from app.schemas.events import ShipmentEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("alert-worker")

GROUP_ID = "alert-worker"

# Redis set of shipments that already have an unresolved alert of each type.
# Without this the worker would raise a fresh alert on every single location
# update while a shipment stays delayed — hundreds of duplicates per minute.
OPEN_KEY = "alerts:open:{}"


def severity_for(delay_hours: float) -> str:
    if delay_hours >= 8:
        return "HIGH"
    if delay_hours >= settings.delay_alert_threshold_hours:
        return "MEDIUM"
    return "LOW"


def create_alert(
    shipment_number: str, alert_type: str, severity: str, message: str
) -> dict | None:
    db = SessionLocal()
    try:
        alert = Alert(
            shipment_number=shipment_number,
            alert_type=alert_type,
            severity=severity,
            message=message,
            status="OPEN",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return {
            "id": alert.id,
            "shipment_number": alert.shipment_number,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "status": alert.status,
            "created_at": alert.created_at,
        }
    except Exception:
        db.rollback()
        log.exception("Could not write alert")
        return None
    finally:
        db.close()


def resolve_alerts(shipment_number: str, alert_type: str) -> int:
    """Close open alerts of a type once the condition clears."""
    db = SessionLocal()
    try:
        result = db.execute(
            update(Alert)
            .where(
                Alert.shipment_number == shipment_number,
                Alert.alert_type == alert_type,
                Alert.status == "OPEN",
            )
            .values(status="RESOLVED", resolved_at=datetime.now(timezone.utc))
        )
        db.commit()
        return result.rowcount or 0
    except Exception:
        db.rollback()
        return 0
    finally:
        db.close()


async def handle_event(e: ShipmentEvent, redis) -> int:
    """Evaluate one event. Returns number of alerts raised."""
    raised = 0
    delay_key = OPEN_KEY.format("DELAY")

    # --- condition cleared: shipment moving again, or delivered ---
    if e.status in ("IN_TRANSIT", "DELIVERED") and not e.delay_hours:
        if await redis.sismember(delay_key, e.shipment_number):
            await redis.srem(delay_key, e.shipment_number)
            n = await asyncio.to_thread(resolve_alerts, e.shipment_number, "DELAY")
            if n:
                await publish_ws(redis, {
                    "type": "ALERT_RESOLVED",
                    "shipment_number": e.shipment_number,
                    "alert_type": "DELAY",
                })

    # --- any position report clears a stale flag ---
    stale_key = OPEN_KEY.format("STALE")
    if await redis.sismember(stale_key, e.shipment_number):
        await redis.srem(stale_key, e.shipment_number)
        n = await asyncio.to_thread(resolve_alerts, e.shipment_number, "STALE")
        if n:
            await publish_ws(redis, {
                "type": "ALERT_RESOLVED",
                "shipment_number": e.shipment_number,
                "alert_type": "STALE",
            })

    # --- delay detection ---
    delay = e.delay_hours or 0.0
    if delay >= settings.delay_alert_threshold_hours:
        # SADD returns 1 only if the member was not already present, so this
        # is an atomic "is this the first time?" check. Two worker replicas
        # racing on the same shipment still produce exactly one alert.
        is_new = await redis.sadd(delay_key, e.shipment_number)
        if is_new:
            sev = severity_for(delay)
            reason = e.delay_reason.value.replace("_", " ").title() if e.delay_reason else "Unknown"
            hrs, mins = int(delay), int((delay % 1) * 60)
            alert = await asyncio.to_thread(
                create_alert,
                e.shipment_number, "DELAY", sev,
                f"Delayed by {hrs}h {mins:02d}m — {reason}",
            )
            if alert:
                raised += 1
                await publish_ws(redis, {"type": "ALERT_CREATED", **alert})
                log.info("  %s  %s  %.1fh  %s", sev, e.shipment_number, delay, reason)

    return raised


async def stale_scanner(redis, stopping: asyncio.Event) -> None:
    """Periodically look for shipments that have gone quiet.

    Note this works on elapsed REAL time, not simulated time. The simulator
    compresses a week-long voyage into ~20 minutes, so a 30-minute gap in
    simulated terms would never occur in a demo. `stale_after_seconds`
    is the real-world equivalent.
    """
    stale_key = OPEN_KEY.format("STALE")
    cutoff_seconds = settings.stale_after_seconds

    while not stopping.is_set():
        try:
            await asyncio.wait_for(stopping.wait(), timeout=15)
            return
        except asyncio.TimeoutError:
            pass

        try:
            now = datetime.now(timezone.utc)
            states = await get_all_states(redis)

            for s in states:
                updated = s.get("updated_at")
                if not updated:
                    continue
                if isinstance(updated, str):
                    updated = datetime.fromisoformat(updated)
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)

                gap = (now - updated).total_seconds()
                if gap < cutoff_seconds:
                    continue

                number = s["shipment_number"]
                if await redis.sadd(stale_key, number):
                    alert = await asyncio.to_thread(
                        create_alert, number, "STALE", "MEDIUM",
                        f"No position update for {int(gap)}s — last seen "
                        f"{s.get('latitude'):.2f}, {s.get('longitude'):.2f}"
                        if s.get("latitude") is not None
                        else f"No position update for {int(gap)}s",
                    )
                    if alert:
                        await publish_ws(redis, {"type": "ALERT_CREATED", **alert})
                        log.info("  STALE  %s  quiet for %ds", number, int(gap))
        except Exception:
            log.exception("Stale scan failed — continuing")


async def run() -> None:
    redis = make_client()
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=GROUP_ID,
        # A different group_id from the state worker means separate offsets:
        # this worker reads every message too, independently.
        auto_offset_reset="latest",
        enable_auto_commit=False,
        max_poll_records=200,
    )
    await consumer.start()
    log.info("Consuming '%s' as group '%s'", settings.kafka_topic, GROUP_ID)
    log.info(
        "Thresholds: delay >= %.1fh, stale > %ds",
        settings.delay_alert_threshold_hours, settings.stale_after_seconds,
    )

    stopping = asyncio.Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())

    scanner = asyncio.create_task(stale_scanner(redis, stopping))
    total = 0

    try:
        while not stopping.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=200)
            if not batches:
                continue

            n = 0
            for _tp, messages in batches.items():
                for msg in messages:
                    try:
                        e = ShipmentEvent.model_validate_json(msg.value)
                    except Exception:
                        continue
                    n += await handle_event(e, redis)

            await consumer.commit()
            total += n
            if n:
                log.info("raised %d alert(s)  |  total %d", n, total)
    finally:
        scanner.cancel()
        await consumer.stop()
        await redis.aclose()
        log.info("Stopped. Raised %d alerts.", total)


if __name__ == "__main__":
    asyncio.run(run())
