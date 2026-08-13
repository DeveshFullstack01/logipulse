from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(80))
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lon: Mapped[float] = mapped_column(Float)
    dest_lat: Mapped[float] = mapped_column(Float)
    dest_lon: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)
    expected_duration_hours: Mapped[float] = mapped_column(Float)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    mode: Mapped[str] = mapped_column(String(16), default="SEA")  # SEA | ROAD | AIR
    status: Mapped[str] = mapped_column(String(24), default="CREATED", index=True)
    risk_level: Mapped[str] = mapped_column(String(12), default="LOW")

    current_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 -> 1.0

    expected_delivery: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estimated_delivery: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delay_reason: Mapped[str | None] = mapped_column(String(48), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    route: Mapped["Route"] = relationship()


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Idempotency key. Replaying the same event twice must NOT create two rows.
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    shipment_number: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


# Powers the shipment timeline query and the replay-by-time-window query.
Index("ix_events_shipment_time", ShipmentEvent.shipment_number, ShipmentEvent.occurred_at)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_number: Mapped[str] = mapped_column(String(32), index=True)
    alert_type: Mapped[str] = mapped_column(String(32))  # DELAY | STALE
    severity: Mapped[str] = mapped_column(String(12), index=True)  # LOW|MEDIUM|HIGH
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
