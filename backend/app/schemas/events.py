"""The event contract.

Every message on the `shipment-events` topic conforms to ShipmentEvent.
The simulator produces these; the state worker and alert worker consume them.
Keeping this in one place means all three agree on the shape.
"""
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    SHIPMENT_CREATED = "SHIPMENT_CREATED"
    SHIPMENT_PICKED_UP = "SHIPMENT_PICKED_UP"
    SHIPMENT_DEPARTED = "SHIPMENT_DEPARTED"
    SHIPMENT_LOCATION_UPDATED = "SHIPMENT_LOCATION_UPDATED"
    SHIPMENT_DELAYED = "SHIPMENT_DELAYED"
    SHIPMENT_DELIVERED = "SHIPMENT_DELIVERED"


class DelayReason(StrEnum):
    PORT_CONGESTION = "PORT_CONGESTION"
    WEATHER = "WEATHER"
    CUSTOMS = "CUSTOMS"
    MECHANICAL = "MECHANICAL"
    UNKNOWN = "UNKNOWN"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ShipmentEvent(BaseModel):
    # Idempotency key. The state worker relies on the unique index on this
    # column, so replaying a message can never create a duplicate row.
    event_id: str = Field(default_factory=lambda: f"evt-{uuid4().hex[:16]}")

    event_type: EventType
    shipment_number: str

    latitude: float | None = None
    longitude: float | None = None
    status: str | None = None
    progress: float | None = None

    speed_kmh: float | None = None
    delay_hours: float | None = None
    delay_reason: DelayReason | None = None
    estimated_delivery: datetime | None = None

    occurred_at: datetime = Field(default_factory=_now)

    def to_json(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @property
    def key(self) -> bytes:
        """Kafka partition key.

        Partitioning by shipment number guarantees that every event for a
        given shipment lands on the same partition, and therefore that a
        consumer sees them in the order they were produced. Without this,
        a DELAYED event could overtake a later LOCATION_UPDATED and leave
        the dashboard showing stale state.
        """
        return self.shipment_number.encode("utf-8")
