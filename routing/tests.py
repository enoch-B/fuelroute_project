from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import SimpleTestCase

from .planner import NoFeasiblePlan, Stop, plan_fuel_stops


class PlannerTests(SimpleTestCase):
    def test_short_trip_needs_no_fuel(self):
        buys, total = plan_fuel_stops([Stop(100, 3.0)], 400)
        self.assertEqual(buys, [])
        self.assertEqual(total, 0)

    def test_buys_only_enough_at_expensive_stop_when_cheaper_ahead(self):
        # 900 mi trip, full tank at start. A (mile 400, $4) then B (mile 700, $3).
        stops = [Stop(400, 4.0), Stop(700, 3.0)]
        buys, total = plan_fuel_stops(stops, 900)
        by_price = {b["stop"].price: b["gallons"] for b in buys}
        # Arrive at A with 100 mi left; cheaper B is 300 mi away -> buy 200 mi (20 gal) at A.
        self.assertAlmostEqual(by_price[4.0], 20.0)
        # At B (no cheaper ahead, dest 200 mi away, fuel 0): buy 20 gal.
        self.assertAlmostEqual(by_price[3.0], 20.0)
        self.assertAlmostEqual(total, 20 * 4.0 + 20 * 3.0)

    def test_fills_up_at_cheapest_then_coasts(self):
        # Cheapest stop first, then pricier ones: fill up at the cheap one.
        stops = [Stop(300, 2.5), Stop(600, 3.5), Stop(900, 3.6)]
        buys, total = plan_fuel_stops(stops, 1200)
        first = buys[0]
        self.assertEqual(first["stop"].price, 2.5)
        self.assertAlmostEqual(first["gallons"], 30.0)   # 300 mi used -> refill to full

    def test_gap_larger_than_range_is_infeasible(self):
        with self.assertRaises(NoFeasiblePlan):
            plan_fuel_stops([Stop(100, 3.0)], 1000)

    def test_total_gallons_cover_trip(self):
        stops = [Stop(m, 3 + (m % 7) / 10) for m in range(50, 2000, 120)]
        buys, _ = plan_fuel_stops(stops, 2000)
        gallons = sum(b["gallons"] for b in buys)
        # Trip needs 200 gal; the starting tank (50 gal) is free; fuel left over is allowed.
        self.assertGreaterEqual(gallons, 150 - 1e-6)
        self.assertLessEqual(gallons, 150 + 1e-6)


class ViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_missing_params(self):
        r = self.client.get("/api/route/")
        self.assertEqual(r.status_code, 400)

    def test_dallas_to_atlanta_with_mocked_router(self):
        # Straight line Dallas -> Atlanta as a stand-in for the OSRM geometry.
        lat = np.linspace(32.78, 33.75, 800)
        lng = np.linspace(-96.80, -84.39, 800)
        coords = np.column_stack([lat, lng])
        geometry = {"type": "LineString", "coordinates": [[x, y] for y, x in coords]}
        with mock.patch("routing.views.get_route", return_value=(coords, 800.0, geometry)) as m:
            r = self.client.get("/api/route/", {"start": "32.78,-96.80", "finish": "33.75,-84.39"})
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(m.call_count, 1)              # exactly one routing call
            self.assertGreaterEqual(len(body["fuel_stops"]), 1)
            self.assertGreater(body["total_fuel_cost"], 0)
            # Cost = sum of per-stop costs; gallons never exceed trip need.
            self.assertAlmostEqual(body["total_fuel_cost"],
                                   sum(s["cost"] for s in body["fuel_stops"]), delta=0.05)
            self.assertLessEqual(body["total_gallons_purchased"], 800 / 10)
            # Second identical request is served from cache: no extra routing call.
            self.client.get("/api/route/", {"start": "32.78,-96.80", "finish": "33.75,-84.39"})
            self.assertEqual(m.call_count, 1)
            # HTML map variant
            h = self.client.get("/api/route/", {"start": "32.78,-96.80",
                                                "finish": "33.75,-84.39", "format": "html"})
            self.assertIn(b"leaflet", h.content.lower())
