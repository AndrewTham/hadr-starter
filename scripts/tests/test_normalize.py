import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hadr.normalize import gdacs_feature_to_evidence, usgs_feature_to_evidence
from hadr.util import parse_epoch


class TestNormalize(unittest.TestCase):
    def test_usgs_coordinates_are_lon_lat_depth(self):
        feat = {
            "id": "us6000tafd",
            "properties": {
                "mag": 3.04, "magType": "ml", "place": "9 km NNE of Avalon",
                "time": 1783342082180, "updated": 1783342799040,
                "alert": None, "status": "automatic", "ids": ",ci41287863,us6000tafd,",
                "title": "M 3.0",
            },
            "geometry": {"type": "Point", "coordinates": [-118.3, 33.4, 12.1]},
        }
        ev = usgs_feature_to_evidence(feat, "2026-07-08T00:00:00Z")
        # lon first, lat second, depth third — the classic swap trap.
        self.assertEqual(ev.lon, -118.3)
        self.assertEqual(ev.lat, 33.4)
        self.assertEqual(ev.depth_km, 12.1)
        self.assertEqual(ev.hazard_type, "earthquake")
        self.assertEqual(ev.external_ids, ["ci41287863", "us6000tafd"])
        # onset round-trips back to the source epoch (seconds), independent of base.
        self.assertAlmostEqual(parse_epoch(ev.onset_time), 1783342082, delta=1)
        self.assertIsNone(ev.pager_level)

    def test_gdacs_hazard_and_impact(self):
        feat = {
            "geometry": {"type": "Point", "coordinates": [141.845, 40.4353]},
            "properties": {
                "eventtype": "EQ", "eventid": 1550421, "episodeid": 1716583,
                "glide": "", "name": "Earthquake in Japan",
                "alertlevel": "Green", "alertscore": 1, "iso3": "JPN",
                "fromdate": "2026-07-06T11:29:36", "datemodified": "2026-07-06T12:09:48",
                "source": "NEIC",
            },
        }
        ev = gdacs_feature_to_evidence(feat, "2026-07-08T00:00:00Z")
        self.assertEqual(ev.hazard_type, "earthquake")
        self.assertEqual(ev.source_event_id, "1550421")
        self.assertEqual(ev.gdacs_level, "Green")
        self.assertEqual(ev.origin_agency, "NEIC")
        self.assertIsNone(ev.glide)  # empty string normalized to None

    def test_gdacs_unknown_eventtype_is_other(self):
        feat = {"geometry": {"coordinates": [0, 0]}, "properties": {"eventtype": "ZZ", "eventid": 1}}
        ev = gdacs_feature_to_evidence(feat, "2026-07-08T00:00:00Z")
        self.assertEqual(ev.hazard_type, "other")


if __name__ == "__main__":
    unittest.main()
