"""Great-circle geometry.

The simulator walks these paths and the frontend redraws them, so an error
here shows up as vessels moving through the wrong ocean.
"""
import pytest

from simulator.geo import haversine_km, interpolate

MUMBAI = (18.9388, 72.8354)
SINGAPORE = (1.2644, 103.8223)
CHENNAI = (13.0827, 80.2707)
LONDON = (51.5074, -0.1278)


class TestDistance:
    def test_matches_published_distance(self):
        # Mumbai to Singapore is about 3,900 km by sea chart
        assert haversine_km(*MUMBAI, *SINGAPORE) == pytest.approx(3900, abs=60)

    def test_zero_for_the_same_point(self):
        assert haversine_km(*MUMBAI, *MUMBAI) == pytest.approx(0, abs=0.001)

    def test_is_symmetric(self):
        assert haversine_km(*MUMBAI, *SINGAPORE) == pytest.approx(
            haversine_km(*SINGAPORE, *MUMBAI)
        )


class TestInterpolation:
    def test_endpoints_are_exact(self):
        assert interpolate(*MUMBAI, *SINGAPORE, 0.0) == pytest.approx(MUMBAI, abs=1e-6)
        assert interpolate(*MUMBAI, *SINGAPORE, 1.0) == pytest.approx(SINGAPORE, abs=1e-6)

    def test_fraction_is_clamped(self):
        assert interpolate(*MUMBAI, *SINGAPORE, -5) == pytest.approx(MUMBAI, abs=1e-6)
        assert interpolate(*MUMBAI, *SINGAPORE, 99) == pytest.approx(SINGAPORE, abs=1e-6)

    def test_arcs_north_of_a_straight_line(self):
        """The reason for spherical interpolation: on a long westbound leg the
        true course runs well north of the naive midpoint."""
        lat, _ = interpolate(*CHENNAI, *LONDON, 0.5)
        naive = (CHENNAI[0] + LONDON[0]) / 2

        assert lat > naive + 5

    def test_halfway_is_halfway_by_distance(self):
        mid = interpolate(*MUMBAI, *SINGAPORE, 0.5)
        total = haversine_km(*MUMBAI, *SINGAPORE)

        assert haversine_km(*MUMBAI, *mid) == pytest.approx(total / 2, rel=0.01)

    def test_identical_points_do_not_divide_by_zero(self):
        assert interpolate(*MUMBAI, *MUMBAI, 0.5) == pytest.approx(MUMBAI, abs=1e-6)
