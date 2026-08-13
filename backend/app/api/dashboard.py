"""Dashboard + analytics endpoints.

The summary blends two sources on purpose: live positions come from Redis
(one round trip for every active shipment) while historical aggregates come
from Postgres. Neither store could serve both well.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from sqlalchemy import case, func, select

from app.cache.client import get_all_states
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Alert, Route, Shipment

router = APIRouter(prefix="/api", tags=["dashboard"])


def _counts() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Shipment.status, func.count()).group_by(Shipment.status)
        ).all()
        by_status = {s: c for s, c in rows}

        delivered = by_status.get("DELIVERED", 0)
        delayed = by_status.get("DELAYED", 0)
        active = sum(c for s, c in by_status.items() if s != "DELIVERED")

        open_alerts = db.scalar(
            select(func.count()).select_from(Alert).where(Alert.status == "OPEN")
        ) or 0

        # Split the delayed population by whether anyone has been paged.
        # gap = how many hours late the current ETA is versus the promise.
        gap_hours = func.extract(
            "epoch", Shipment.estimated_delivery - Shipment.expected_delivery
        ) / 3600.0
        threshold = settings.delay_alert_threshold_hours

        # "At risk" = slipping, but not yet bad enough to raise an alert.
        # These are the ones an operations manager can still save.
        at_risk = db.scalar(
            select(func.count()).select_from(Shipment).where(
                Shipment.status.notin_(["DELIVERED"]),
                Shipment.estimated_delivery.isnot(None),
                gap_hours > 0,
                gap_hours < threshold,
            )
        ) or 0

        total_finished = delivered
        on_time = db.scalar(
            select(func.count()).select_from(Shipment).where(
                Shipment.status == "DELIVERED",
                case(
                    (Shipment.estimated_delivery.is_(None), True),
                    else_=Shipment.estimated_delivery <= Shipment.expected_delivery,
                ),
            )
        ) or 0

        rate = round(100.0 * on_time / total_finished, 1) if total_finished else 100.0

        return {
            "active": active,
            "delayed": delayed,
            "at_risk": at_risk,
            "delivered": delivered,
            "open_alerts": open_alerts,
            "on_time_rate": rate,
            "by_status": by_status,
        }
    finally:
        db.close()


@router.get("/dashboard/summary")
async def dashboard_summary(request: Request):
    counts = _counts()
    try:
        live = await get_all_states(request.app.state.redis)
        counts["live_positions"] = len(live)
    except Exception:
        # Redis down: the dashboard still renders from Postgres, just without
        # live positions. Degraded, not broken.
        counts["live_positions"] = None
        counts["degraded"] = True
    return counts


@router.get("/analytics")
def analytics():
    db = SessionLocal()
    try:
        reasons = db.execute(
            select(Shipment.delay_reason, func.count())
            .where(Shipment.delay_reason.isnot(None))
            .group_by(Shipment.delay_reason)
            .order_by(func.count().desc())
        ).all()
        total_reasons = sum(c for _, c in reasons) or 1

        route_rows = db.execute(
            select(
                Route.origin, Route.destination,
                func.count(Shipment.id).label("total"),
                func.sum(case((Shipment.status == "DELAYED", 1), else_=0)).label("delayed"),
            )
            .join(Shipment, Shipment.route_id == Route.id)
            .group_by(Route.id, Route.origin, Route.destination)
            .order_by(func.count(Shipment.id).desc())
        ).all()

        routes = []
        for origin, dest, total, delayed in route_rows:
            delayed = delayed or 0
            routes.append({
                "route": f"{origin} → {dest}",
                "origin": origin,
                "destination": dest,
                "shipments": total,
                "delayed": delayed,
                "on_time_pct": round(100.0 * (total - delayed) / total, 1) if total else 100.0,
            })

        since = datetime.now(timezone.utc) - timedelta(days=7)
        daily = db.execute(
            select(
                func.date(Alert.created_at).label("day"),
                func.count().label("alerts"),
            )
            .where(Alert.created_at >= since)
            .group_by(func.date(Alert.created_at))
            .order_by(func.date(Alert.created_at))
        ).all()

        return {
            "delay_reasons": [
                {
                    "reason": r.replace("_", " ").title(),
                    "count": c,
                    "pct": round(100.0 * c / total_reasons, 1),
                }
                for r, c in reasons
            ],
            "routes": routes,
            "alerts_by_day": [{"day": str(d), "alerts": c} for d, c in daily],
        }
    finally:
        db.close()
