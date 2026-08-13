"""Alert endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from app.cache.client import publish_ws
from app.db.session import SessionLocal
from app.models import Alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _serialize(a: Alert) -> dict:
    return {
        "id": a.id,
        "shipment_number": a.shipment_number,
        "alert_type": a.alert_type,
        "severity": a.severity,
        "message": a.message,
        "status": a.status,
        "created_at": a.created_at,
        "resolved_at": a.resolved_at,
    }


@router.get("")
def list_alerts(
    status: str = Query("OPEN"),
    severity: str | None = None,
    limit: int = Query(50, le=200),
):
    db = SessionLocal()
    try:
        stmt = select(Alert)
        if status.upper() != "ALL":
            stmt = stmt.where(Alert.status == status.upper())
        if severity:
            stmt = stmt.where(Alert.severity == severity.upper())

        rows = db.execute(
            stmt.order_by(Alert.created_at.desc()).limit(limit)
        ).scalars().all()

        # Highest severity first, then most recent — the order an operator
        # actually wants to work through them in.
        rows = sorted(
            rows,
            key=lambda a: (SEVERITY_ORDER.get(a.severity, 9), -a.created_at.timestamp()),
        )

        counts = dict(
            db.execute(
                select(Alert.severity, func.count())
                .where(Alert.status == "OPEN")
                .group_by(Alert.severity)
            ).all()
        )

        return {
            "count": len(rows),
            "open_by_severity": counts,
            "alerts": [_serialize(a) for a in rows],
        }
    finally:
        db.close()


@router.patch("/{alert_id}/resolve")
async def resolve_alert(alert_id: int, request: Request):
    db = SessionLocal()
    try:
        alert = db.get(Alert, alert_id)
        if not alert:
            raise HTTPException(404, f"Alert {alert_id} not found")
        if alert.status == "RESOLVED":
            return _serialize(alert)

        alert.status = "RESOLVED"
        alert.resolved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alert)
        data = _serialize(alert)
    finally:
        db.close()

    # Tell every open dashboard, so two operators don't work the same alert.
    try:
        await publish_ws(request.app.state.redis, {"type": "ALERT_RESOLVED", **data})
    except Exception:
        pass

    return data
