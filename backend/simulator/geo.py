"""Great-circle interpolation.

Linear interpolation between two lat/lon points looks wrong on a map for
long routes — a Chennai-to-London shipment would cut straight across the
page instead of arcing north the way real routes do. Slerp (spherical
linear interpolation) walks the actual shortest path over the sphere.
"""
import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two points on the globe."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def interpolate(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """Point at `fraction` (0..1) along the great circle from 1 to 2."""
    fraction = max(0.0, min(1.0, fraction))

    p1, l1 = math.radians(lat1), math.radians(lon1)
    p2, l2 = math.radians(lat2), math.radians(lon2)

    # Angular distance between the two points
    d = 2 * math.asin(
        math.sqrt(
            math.sin((p2 - p1) / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
        )
    )

    if d < 1e-9:  # same point — nothing to interpolate
        return lat1, lon1

    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)

    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)

    lat = math.atan2(z, math.sqrt(x * x + y * y))
    lon = math.atan2(y, x)
    return math.degrees(lat), math.degrees(lon)
