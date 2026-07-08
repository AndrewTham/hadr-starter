import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hadr.util import haversine_km, parse_epoch


class TestHaversine(unittest.TestCase):
    def test_near_antipode_does_not_raise(self):
        # Antipode of Singapore (~1.35S, 76.18W). Float rounding can push the
        # haversine term just over 1; without clamping, math.asin would raise a
        # domain ValueError. Must return ~half Earth's circumference instead.
        d = haversine_km(-1.3521, -76.1802, 1.3521, 103.8198)
        self.assertIsNotNone(d)
        self.assertGreater(d, 19000)

    def test_none_coords_returns_none(self):
        self.assertIsNone(haversine_km(None, 1.0, 2.0, 3.0))

    def test_zero_distance(self):
        self.assertAlmostEqual(haversine_km(1.35, 103.8, 1.35, 103.8), 0.0, places=6)


class TestParseEpoch(unittest.TestCase):
    def test_z_and_naive_agree(self):
        # The 'newest wins' fold depends on these two forms parsing equal.
        self.assertEqual(
            parse_epoch("2026-07-08T00:00:00Z"), parse_epoch("2026-07-08T00:00:00")
        )

    def test_none_and_garbage(self):
        self.assertIsNone(parse_epoch(None))
        self.assertIsNone(parse_epoch("not-a-date"))


if __name__ == "__main__":
    unittest.main()
