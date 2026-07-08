import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hadr.models import Situation
from hadr.relevance import rank_for_singapore, sg_tier


def sit(sid, hazard, lat, lon, iso3=None, pager=None, gdacs=None):
    return Situation(
        situation_id=sid, hazard_type=hazard, lat=lat, lon=lon, iso3=iso3,
        pager_level=pager, gdacs_level=gdacs, sources=["gdacs"] if gdacs else ["usgs"],
    )


class TestSgTier(unittest.TestCase):
    def test_france_wildfire_is_global(self):
        # ~10,600 km away, longitude far west of the SE-Asia box — must never
        # read as Singapore-relevant just because it's a wildfire.
        s = sit("fr", "wildfire", 46.6, 2.4, iso3="FRA", gdacs="Orange")
        self.assertEqual(sg_tier(s), "GLOBAL")

    def test_philippines_cyclone_is_regional_not_direct(self):
        # In-region but ~2,000+ km off; Singapore sits outside the cyclone belt.
        s = sit("tc", "tropical_cyclone", 14.5, 122.0, iso3="PHL", gdacs="Red")
        self.assertEqual(sg_tier(s), "REGIONAL")

    def test_banda_sea_quake_regional_despite_no_iso3(self):
        # USGS-only quake: iso3 is None. The lat/lon box must still catch it —
        # this is exactly the regional tsunami-source case iso3 would miss.
        s = sit("bs", "earthquake", -6.0, 130.0, iso3=None, pager="orange")
        self.assertIsNone(s.iso3)
        self.assertEqual(sg_tier(s), "REGIONAL")

    def test_malacca_quake_is_direct(self):
        # ~270 km from Singapore.
        s = sit("mc", "earthquake", 2.0, 101.5, iso3="MYS", pager="yellow")
        self.assertEqual(sg_tier(s), "DIRECT")

    def test_distant_severe_quake_is_global_but_reportable(self):
        # A red-PAGER quake in Türkiye is far (GLOBAL) but still matters to a
        # deploying agency — relevance tiers it, impact keeps it in scope.
        s = sit("tr", "earthquake", 37.2, 37.0, iso3="TUR", pager="red")
        self.assertEqual(sg_tier(s), "GLOBAL")
        self.assertTrue(s.reportable)

    def test_no_coords_falls_back_to_iso3(self):
        s = sit("x", "flood", None, None, iso3="THA", gdacs="Orange")
        self.assertEqual(sg_tier(s), "REGIONAL")
        s2 = sit("y", "flood", None, None, iso3="BRA", gdacs="Orange")
        self.assertEqual(sg_tier(s2), "GLOBAL")


class TestRanking(unittest.TestCase):
    def test_tier_then_impact_ordering(self):
        direct = sit("d", "earthquake", 2.0, 101.5, pager="yellow")       # DIRECT
        regional_red = sit("r", "tropical_cyclone", 14.5, 122.0, gdacs="Red")   # REGIONAL rank3
        regional_orange = sit("r2", "flood", -6.0, 130.0, gdacs="Orange")       # REGIONAL rank2
        global_red = sit("g", "earthquake", 37.2, 37.0, pager="red")           # GLOBAL rank3
        order = [s.situation_id for s in rank_for_singapore(
            [global_red, regional_orange, direct, regional_red])]
        # DIRECT first, then REGIONAL (red before orange), then GLOBAL — nothing dropped.
        self.assertEqual(order, ["d", "r", "r2", "g"])
        self.assertEqual(len(order), 4)


if __name__ == "__main__":
    unittest.main()
