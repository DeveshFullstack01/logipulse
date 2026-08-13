"""API surface tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
class TestHealth:
    async def test_reports_each_dependency(self, client):
        r = await client.get("/health")
        body = r.json()

        assert r.status_code == 200
        assert body["status"] in ("healthy", "degraded")
        assert set(body["dependencies"]) == {"postgres", "redis"}

    async def test_exposes_websocket_count(self, client):
        body = (await client.get("/health")).json()
        assert body["websocket_connections"] == 0


@pytest.mark.asyncio
class TestShipments:
    async def test_lists_shipments(self, client, shipment):
        body = (await client.get("/api/shipments")).json()

        assert body["total"] == 1
        assert body["shipments"][0]["shipment_number"] == "SHP-TEST-1"
        assert body["shipments"][0]["route"] == "Mumbai → Singapore"

    async def test_filters_by_status(self, client, shipment):
        assert (await client.get("/api/shipments?status=DELAYED")).json()["total"] == 0
        assert (await client.get("/api/shipments?status=IN_TRANSIT")).json()["total"] == 1

    async def test_searches_by_port(self, client, shipment):
        assert (await client.get("/api/shipments?search=Singapore")).json()["total"] == 1
        assert (await client.get("/api/shipments?search=Reykjavik")).json()["total"] == 0

    async def test_detail_includes_the_plotted_course(self, client, shipment):
        body = (await client.get("/api/shipments/SHP-TEST-1")).json()

        # The frontend draws the great circle from these four numbers.
        for key in ("origin_lat", "origin_lon", "dest_lat", "dest_lon"):
            assert body[key] is not None

    async def test_unknown_shipment_is_a_404(self, client, shipment):
        assert (await client.get("/api/shipments/SHP-NOPE")).status_code == 404

    async def test_timeline_is_empty_before_any_events(self, client, shipment):
        body = (await client.get("/api/shipments/SHP-TEST-1/timeline")).json()
        assert body["events"] == []


@pytest.mark.asyncio
class TestDashboard:
    async def test_summary_has_every_reading(self, client, shipment):
        body = (await client.get("/api/dashboard/summary")).json()

        for key in ("active", "delayed", "at_risk", "delivered",
                    "open_alerts", "on_time_rate"):
            assert key in body
        assert body["active"] == 1

    async def test_analytics_shape(self, client, shipment):
        body = (await client.get("/api/analytics")).json()

        assert set(body) >= {"delay_reasons", "routes", "alerts_by_day"}
        assert body["routes"][0]["route"] == "Mumbai → Singapore"


@pytest.mark.asyncio
class TestChaos:
    async def test_congesting_a_port_is_recorded(self, client):
        await client.delete("/api/chaos")
        body = (await client.post("/api/chaos/port/Singapore")).json()

        assert "Singapore" in body["congest_ports"]
        assert body["delay_reason"] == "PORT_CONGESTION"

    async def test_congesting_twice_does_not_duplicate(self, client):
        await client.delete("/api/chaos")
        await client.post("/api/chaos/port/Dubai")
        body = (await client.post("/api/chaos/port/Dubai")).json()

        assert body["congest_ports"].count("Dubai") == 1

    async def test_clearing_resets_every_condition(self, client):
        await client.post("/api/chaos/storm")
        body = (await client.delete("/api/chaos")).json()

        assert body["delay_all"] is False
        assert body["congest_ports"] == []
