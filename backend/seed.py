"""Seed routes + shipments. Run once: python seed.py"""
import random
from datetime import datetime, timedelta, timezone

from app.db.session import Base, SessionLocal, engine
from app.models import Route, Shipment

ROUTES = [
    # origin, dest, o_lat, o_lon, d_lat, d_lon, km, hours, mode
    ("Mumbai", "Singapore", 18.9388, 72.8354, 1.2644, 103.8223, 3900, 168, "SEA"),
    ("Delhi", "Dubai", 28.5562, 77.1000, 25.2532, 55.3657, 2190, 4, "AIR"),
    ("Chennai", "London", 13.0827, 80.2707, 51.5074, -0.1278, 8250, 336, "SEA"),
    ("Mumbai", "Dubai", 18.9388, 72.8354, 25.2697, 55.3094, 1930, 96, "SEA"),
    ("Kolkata", "Bangkok", 22.5726, 88.3639, 13.7563, 100.5018, 1660, 72, "SEA"),
    ("Mumbai", "Ahmedabad", 19.0760, 72.8777, 23.0225, 72.5714, 530, 11, "ROAD"),
    ("Delhi", "Jabalpur", 28.6139, 77.2090, 23.1815, 79.9864, 830, 15, "ROAD"),
    ("Cochin", "Rotterdam", 9.9312, 76.2673, 51.9244, 4.4777, 9700, 384, "SEA"),
]

STATUSES = ["CREATED", "PICKED_UP", "IN_TRANSIT", "IN_TRANSIT", "IN_TRANSIT", "DELIVERED"]


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(Route).count() == 0:
            for o, d, ola, olo, dla, dlo, km, hrs, mode in ROUTES:
                db.add(Route(
                    origin=o, destination=d,
                    origin_lat=ola, origin_lon=olo,
                    dest_lat=dla, dest_lon=dlo,
                    distance_km=km, expected_duration_hours=hrs,
                ))
            db.commit()

        routes = db.query(Route).all()
        existing = db.query(Shipment).count()
        now = datetime.now(timezone.utc)

        for i in range(existing + 1, existing + 121):
            route = random.choice(routes)
            status = random.choice(STATUSES)
            progress = 0.0 if status == "CREATED" else (
                1.0 if status == "DELIVERED" else round(random.uniform(0.05, 0.9), 3)
            )
            lat = route.origin_lat + (route.dest_lat - route.origin_lat) * progress
            lon = route.origin_lon + (route.dest_lon - route.origin_lon) * progress

            db.add(Shipment(
                shipment_number=f"SHP-{1000 + i}",
                route_id=route.id,
                mode=random.choice(["SEA", "ROAD", "AIR"]),
                status=status,
                progress=progress,
                current_lat=lat,
                current_lon=lon,
                expected_delivery=now + timedelta(
                    hours=route.expected_duration_hours * (1 - progress)
                ),
            ))
        db.commit()
        print(f"Seeded. routes={db.query(Route).count()} shipments={db.query(Shipment).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
