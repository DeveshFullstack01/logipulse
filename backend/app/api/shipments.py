"""Shipment endpoints."""
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, or_, select

from app.cache.client import get_shipment_state
from app.db.session import SessionLocal
from app.models import Route, Shipment, ShipmentEvent

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


def _serialize(s: Shipment, r: Route) -> dict:
    return {
        "shipment_number": s.shipment_number,
        "status": s.status,
        "mode": s.mode,
        "origin": r.origin,
        "destination": r.destination,
        "route": f"{r.origin} → {r.destination}",
        "origin_lat": r.origin_lat, "origin_lon": r.origin_lon,
        "dest_lat": r.dest_lat, "dest_lon": r.dest_lon,
        "current_lat": s.current_lat, "current_lon": s.current_lon,
        "progress": s.progress,
        "distance_km": r.distance_km,
        "expected_delivery": s.expected_delivery,
        "estimated_delivery": s.estimated_delivery,
        "delay_reason": s.delay_reason,
        "risk_level": s.risk_level,
    }


@router.get("")
def list_shipments(
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    db = SessionLocal()
    try:
        stmt = select(Shipment, Route).join(Route, Shipment.route_id == Route.id)
        count_stmt = select(func.count()).select_from(Shipment).join(
            Route, Shipment.route_id == Route.id
        )

        if status:
            stmt = stmt.where(Shipment.status == status.upper())
            count_stmt = count_stmt.where(Shipment.status == status.upper())
        if search:
            like = f"%{search}%"
            cond = or_(
                Shipment.shipment_number.ilike(like),
                Route.origin.ilike(like),
                Route.destination.ilike(like),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        rows = db.execute(
            stmt.order_by(Shipment.updated_at.desc()).limit(limit).offset(offset)
        ).all()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "shipments": [_serialize(s, r) for s, r in rows],
        }
    finally:
        db.close()


@router.get("/{shipment_number}")
async def get_shipment(shipment_number: str, request: Request):
    """Detail view. Postgres holds the durable record; Redis may hold a
    fresher position, so we overlay it when present."""
    db = SessionLocal()
    try:
        row = db.execute(
            select(Shipment, Route)
            .join(Route, Shipment.route_id == Route.id)
            .where(Shipment.shipment_number == shipment_number)
        ).first()
        if not row:
            raise HTTPException(404, f"Shipment {shipment_number} not found")
        data = _serialize(*row)
    finally:
        db.close()

    try:
        live = await get_shipment_state(request.app.state.redis, shipment_number)
        if live:
            data["live"] = live
            if live.get("latitude") is not None:
                data["current_lat"] = live["latitude"]
                data["current_lon"] = live["longitude"]
    except Exception:
        data["live"] = None

    return data


@router.get("/{shipment_number}/timeline")
def timeline(shipment_number: str, limit: int = Query(100, le=500)):
    """Event history. This is the payoff for storing every event rather than
    only the current state — the whole journey is reconstructible."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(ShipmentEvent)
            .where(ShipmentEvent.shipment_number == shipment_number)
            .order_by(ShipmentEvent.occurred_at.desc())
            .limit(limit)
        ).scalars().all()

        return {
            "shipment_number": shipment_number,
            "count": len(rows),
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "status": e.status,
                    "latitude": e.latitude,
                    "longitude": e.longitude,
                    "occurred_at": e.occurred_at,
                    "delay_hours": (e.payload or {}).get("delay_hours"),
                    "delay_reason": (e.payload or {}).get("delay_reason"),
                }
                for e in rows
            ],
        }
    finally:
        db.close()
