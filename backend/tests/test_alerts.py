"""Alert engine behaviour.

The important property is not "a delay makes an alert" — it is that a
shipment which stays delayed for ten minutes makes exactly ONE alert, and
that the alert closes itself when the shipment recovers.
"""
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Alert
from app.schemas.events import DelayReason, EventType, ShipmentEvent as Event
from workers.alert_worker import handle_event, severity_for


def _delayed(hours: float, number="SHP-TEST-1") -> Event:
    return Event(
        event_type=EventType.SHIPMENT_DELAYED,
        shipment_number=number,
        status="DELAYED",
        delay_hours=hours,
        delay_reason=DelayReason.PORT_CONGESTION,
        latitude=14.0, longitude=81.0,
    )


def _moving(number="SHP-TEST-1") -> Event:
    return Event(
        event_type=EventType.SHIPMENT_LOCATION_UPDATED,
        shipment_number=number,
        status="IN_TRANSIT",
        latitude=15.0, longitude=82.0,
    )


class TestSeverity:
    def test_bands(self):
        assert severity_for(9.0) == "HIGH"
        assert severity_for(8.0) == "HIGH"
        assert severity_for(5.5) == "MEDIUM"
        assert severity_for(settings.delay_alert_threshold_hours) == "MEDIUM"
        assert severity_for(1.0) == "LOW"


@pytest.mark.asyncio
class TestDelayAlerts:
    async def test_a_delay_past_the_threshold_raises_one_alert(self, db, shipment, redis):
        raised = await handle_event(_delayed(6.0), redis)

        assert raised == 1
        alert = db.scalar(select(Alert))
        assert alert.severity == "MEDIUM"
        assert alert.status == "OPEN"
        assert "Port Congestion" in alert.message

    async def test_a_delay_under_the_threshold_raises_nothing(self, db, shipment, redis):
        assert await handle_event(_delayed(1.5), redis) == 0
        assert db.scalar(select(func.count()).select_from(Alert)) == 0

    async def test_a_shipment_that_stays_delayed_alerts_only_once(self, db, shipment, redis):
        """Without deduplication this would raise an alert on every position
        report — hundreds a minute for a single stuck vessel."""
        total = 0
        for _ in range(25):
            total += await handle_event(_delayed(6.0), redis)

        assert total == 1
        assert db.scalar(select(func.count()).select_from(Alert)) == 1

    async def test_recovery_closes_the_alert(self, db, shipment, redis):
        await handle_event(_delayed(6.0), redis)
        await handle_event(_moving(), redis)

        db.expire_all()
        alert = db.scalar(select(Alert))
        assert alert.status == "RESOLVED"
        assert alert.resolved_at is not None

    async def test_a_second_delay_after_recovery_alerts_again(self, db, shipment, redis):
        await handle_event(_delayed(6.0), redis)
        await handle_event(_moving(), redis)
        raised = await handle_event(_delayed(7.0), redis)

        assert raised == 1, "a fresh delay after recovery is a new problem"
        assert db.scalar(select(func.count()).select_from(Alert)) == 2

    async def test_different_shipments_alert_independently(self, db, shipment, redis):
        a = await handle_event(_delayed(6.0, "SHP-A"), redis)
        b = await handle_event(_delayed(6.0, "SHP-B"), redis)

        assert (a, b) == (1, 1)
        assert db.scalar(select(func.count()).select_from(Alert)) == 2
