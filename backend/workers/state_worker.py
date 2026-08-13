"""State worker.

Consumes `shipment-events`, and for each event:
  1. appends it to the Postgres event log (deduplicated by event_id)
  2. updates the shipment's current row in Postgres
  3. writes current state to Redis
  4. publishes to the ws:broadcast channel so browsers see it

Runs as its own process:  python -m workers.state_worker
"""
import asyncio
import json
import logging
import signal

from aiokafka import AIOKafkaConsumer
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.cache.client import make_client, publish_ws, set_shipment_state
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Shipment, ShipmentEvent as ShipmentEventRow
from app.schemas.events import ShipmentEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("state-worker")

GROUP_ID = "state-worker"


def persist_batch(events: list[ShipmentEvent]) -> list[ShipmentEvent]:
    """Write a batch to Postgres. Returns only the events that were new.

    Idempotency lives here. `event_id` has a unique index, so ON CONFLICT
    DO NOTHING makes reprocessing a partition harmless: if the worker
    crashes after handling a message but before committing its offset,
    Kafka redelivers it and this insert quietly does nothing.
    """
    if not events:
        return []

    db = SessionLocal()
    try:
        rows = [
            {
                "event_id": e.event_id,
                "shipment_number": e.shipment_number,
                "event_type": e.event_type.value,
                "latitude": e.latitude,
                "longitude": e.longitude,
                "status": e.status,
                "occurred_at": e.occurred_at,
                "payload": json.loads(e.model_dump_json()),
            }
            for e in events
        ]

        stmt = (
            pg_insert(ShipmentEventRow)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(ShipmentEventRow.event_id)
        )
        inserted = {r[0] for r in db.execute(stmt).fetchall()}

        # Only the newest event per shipment matters for the current row.
        latest: dict[str, ShipmentEvent] = {}
        for e in events:
            if e.event_id not in inserted:
                continue
            prev = latest.get(e.shipment_number)
            if prev is None or e.occurred_at >= prev.occurred_at:
                latest[e.shipment_number] = e

        for number, e in latest.items():
            values = {"status": e.status} if e.status else {}
            if e.latitude is not None:
                values["current_lat"] = e.latitude
                values["current_lon"] = e.longitude
            if e.progress is not None:
                values["progress"] = e.progress
            if e.estimated_delivery is not None:
                values["estimated_delivery"] = e.estimated_delivery
            if e.delay_reason is not None:
                values["delay_reason"] = e.delay_reason.value
            if values:
                db.execute(
                    update(Shipment)
                    .where(Shipment.shipment_number == number)
                    .values(**values)
                )

        db.commit()
        return [e for e in events if e.event_id in inserted]

    except Exception:
        db.rollback()
        log.exception("Batch failed — rolled back")
        return []
    finally:
        db.close()


async def handle_batch(events: list[ShipmentEvent], redis) -> int:
    """Persist, then update Redis and notify browsers."""
    # SQLAlchemy here is synchronous; running it in a thread keeps the event
    # loop free so Kafka heartbeats don't stall on a slow commit.
    fresh = await asyncio.to_thread(persist_batch, events)
    if not fresh:
        return 0

    pipe_tasks = []
    for e in fresh:
        state = {
            "shipment_number": e.shipment_number,
            "status": e.status,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "progress": e.progress,
            "speed_kmh": e.speed_kmh,
            "delay_hours": e.delay_hours,
            "delay_reason": e.delay_reason.value if e.delay_reason else None,
            "estimated_delivery": e.estimated_delivery,
            "updated_at": e.occurred_at,
        }
        pipe_tasks.append(set_shipment_state(redis, e.shipment_number, state))

    await asyncio.gather(*pipe_tasks, return_exceptions=True)

    # One message per event so the UI can animate each marker individually.
    await asyncio.gather(*[
        publish_ws(redis, {
            "type": "SHIPMENT_UPDATED",
            "shipment_number": e.shipment_number,
            "status": e.status,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "progress": e.progress,
            "delay_hours": e.delay_hours,
            "delay_reason": e.delay_reason.value if e.delay_reason else None,
            "event_type": e.event_type.value,
            "occurred_at": e.occurred_at,
        })
        for e in fresh
    ], return_exceptions=True)

    return len(fresh)


async def run() -> None:
    redis = make_client()
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=GROUP_ID,
        # Start from the beginning of the log the first time this group runs.
        # Every event the simulator produced before the worker existed gets
        # processed — replay for free, and proof the log is durable.
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=200,
    )
    await consumer.start()
    log.info("Consuming '%s' as group '%s'", settings.kafka_topic, GROUP_ID)

    stopping = asyncio.Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())

    processed = skipped = 0
    try:
        while not stopping.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=200)
            if not batches:
                continue

            events: list[ShipmentEvent] = []
            for _tp, messages in batches.items():
                for msg in messages:
                    try:
                        events.append(ShipmentEvent.model_validate_json(msg.value))
                    except Exception:
                        # A malformed message must not kill the consumer.
                        # Log it, drop it, keep going.
                        skipped += 1
                        log.warning("Bad message at offset %s — skipped", msg.offset)

            n = await handle_batch(events, redis)
            processed += n

            # Commit only after the batch is safely persisted. Crash before
            # this and Kafka replays the batch; the event_id index makes
            # that a no-op.
            await consumer.commit()

            log.info(
                "batch: %-3d events  |  %-3d new  |  total %-6d  skipped %d",
                len(events), n, processed, skipped,
            )
    finally:
        await consumer.stop()
        await redis.aclose()
        log.info("Stopped. Processed %d events.", processed)


if __name__ == "__main__":
    asyncio.run(run())
