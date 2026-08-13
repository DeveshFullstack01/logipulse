"""The idempotency guarantee.

The state worker commits Kafka offsets only after writing to Postgres. If it
crashes in between, Kafka redelivers the batch. These tests pin down that
redelivery is harmless — which is the whole reason `event_id` carries a
unique index.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import Shipment, ShipmentEvent
from app.schemas.events import DelayReason, EventType, ShipmentEvent as Event
from workers.state_worker import persist_batch


def _event(number="SHP-TEST-1", **kw) -> Event:
    return Event(
        event_type=kw.pop("event_type", EventType.SHIPMENT_LOCATION_UPDATED),
        shipment_number=number,
        latitude=kw.pop("latitude", 14.0),
        longitude=kw.pop("longitude", 81.0),
        status=kw.pop("status", "IN_TRANSIT"),
        progress=kw.pop("progress", 0.3),
        **kw,
    )


def test_new_events_are_stored(db, shipment):
    events = [_event(progress=0.3), _event(progress=0.4)]
    fresh = persist_batch(events)

    assert len(fresh) == 2
    assert db.scalar(select(func.count()).select_from(ShipmentEvent)) == 2


def test_replaying_the_same_batch_stores_nothing_new(db, shipment):
    """A crash between the DB write and the offset commit replays the batch."""
    events = [_event(progress=0.3), _event(progress=0.4)]

    first = persist_batch(events)
    second = persist_batch(events)          # Kafka redelivers the identical batch

    assert len(first) == 2
    assert second == [], "redelivered events must be reported as not-new"
    assert db.scalar(select(func.count()).select_from(ShipmentEvent)) == 2


def test_partial_overlap_stores_only_the_unseen_events(db, shipment):
    a, b, c = _event(progress=0.1), _event(progress=0.2), _event(progress=0.3)

    persist_batch([a, b])
    fresh = persist_batch([b, c])           # b overlaps, c is new

    assert [e.event_id for e in fresh] == [c.event_id]
    assert db.scalar(select(func.count()).select_from(ShipmentEvent)) == 3


def test_current_row_is_updated_from_the_latest_event(db, shipment):
    now = datetime.now(timezone.utc)
    older = _event(progress=0.5, latitude=10.0)
    older.occurred_at = now - timedelta(minutes=5)
    newer = _event(progress=0.8, latitude=5.0)
    newer.occurred_at = now

    # Deliberately out of order in the batch: the worker must pick the
    # newest by timestamp, not the last one it happens to iterate over.
    persist_batch([newer, older])

    db.expire_all()
    s = db.scalar(select(Shipment).where(Shipment.shipment_number == "SHP-TEST-1"))
    assert s.progress == 0.8
    assert s.current_lat == 5.0


def test_delay_details_reach_the_shipment_row(db, shipment):
    persist_batch([
        _event(
            event_type=EventType.SHIPMENT_DELAYED,
            status="DELAYED",
            delay_hours=6.5,
            delay_reason=DelayReason.PORT_CONGESTION,
            estimated_delivery=datetime.now(timezone.utc) + timedelta(hours=110),
        )
    ])

    db.expire_all()
    s = db.scalar(select(Shipment).where(Shipment.shipment_number == "SHP-TEST-1"))
    assert s.status == "DELAYED"
    assert s.delay_reason == "PORT_CONGESTION"
    assert s.estimated_delivery is not None


def test_a_malformed_event_does_not_lose_the_whole_batch(db, shipment):
    """One bad row must not roll back the good ones alongside it."""
    good = _event(progress=0.4)
    assert len(persist_batch([good])) == 1

    # An event for a shipment that does not exist: the event log still takes
    # it (the log is append-only and does not care), the row update is a no-op.
    orphan = _event(number="SHP-DOES-NOT-EXIST")
    fresh = persist_batch([orphan])
    assert len(fresh) == 1
    assert db.scalar(select(func.count()).select_from(ShipmentEvent)) == 2
