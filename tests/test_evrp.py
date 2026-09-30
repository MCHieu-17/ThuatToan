import collections
import math
import unittest

from evrp.__main__ import BENCHMARKS, exact_tsp
from evrp.core import (charge_cost, electricity_price, interpolate, load_instance,
                       make_releases, mst_double_tree, solve_online)


class EVRPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance = load_instance(BENCHMARKS[0])

    def test_benchmark_is_read_from_original_archive(self):
        self.assertEqual(len(self.instance.customers), 10)
        self.assertEqual(len(self.instance.stations), 2)
        self.assertEqual(self.instance.battery_wh, 16000)
        self.assertIn("fast", self.instance.curves)
        for name in BENCHMARKS:
            self.assertEqual(load_instance(name).name, name)

    def test_nonlinear_charging_and_tariff_boundary(self):
        curve = self.instance.curves["fast"]
        self.assertAlmostEqual(interpolate(curve, 13600), 0.31)
        self.assertAlmostEqual(interpolate(curve, 0.31, inverse=True), 13600)
        self.assertGreater(interpolate(curve, 16000) - interpolate(curve, 15200),
                           interpolate(curve, 15200) - interpolate(curve, 13600))
        # Two equal charging intervals span a 1-to-3 tariff boundary.
        simple = ((0.0, 0.0), (2000.0, 2.0))
        self.assertAlmostEqual(charge_cost(simple, 0, 2000, 1.0), 4.0)
        self.assertEqual(electricity_price(2), 3.0)

    def test_releases_are_reproducible(self):
        a = make_releases(self.instance, 0.5, 42)
        self.assertEqual(a, make_releases(self.instance, 0.5, 42))
        self.assertEqual(sum(t > 0 for t in a.values()), 5)
        self.assertTrue(all(0 <= t <= self.instance.max_route_hours / 2 for t in a.values()))

    def test_online_trace_serves_each_customer_once_and_respects_battery(self):
        releases = make_releases(self.instance, 0.5, 0)
        for method in ("greedy", "ga", "ga_vns"):
            result = solve_online(self.instance, releases, method, 0, 0.05)
            visits = [e for route in result["routes"].values() for e in route
                      if e["kind"] == "visit"]
            counts = collections.Counter(e["node"] for e in visits)
            self.assertEqual(set(counts), set(self.instance.customers))
            self.assertTrue(all(v == 1 for v in counts.values()))
            for visit in visits:
                self.assertGreaterEqual(visit["start"], releases[visit["node"]] - 1e-8)
            for route in result["routes"].values():
                for event in route:
                    self.assertGreaterEqual(event["battery_after"], -1e-6)
                    self.assertLessEqual(event["battery_after"], self.instance.battery_wh + 1e-6)
                self.assertTrue(all(a["end"] <= b["start"] + 1e-7
                                    for a, b in zip(route, route[1:])))

    def test_mst_tour_bound_on_small_special_case(self):
        tour, distance, mst = mst_double_tree(self.instance, self.instance.customers)
        optimum = exact_tsp(self.instance)
        self.assertEqual(set(tour), {0, *self.instance.customers})
        self.assertLessEqual(distance, 2 * mst + 1e-8)
        self.assertLessEqual(mst, optimum + 1e-8)


if __name__ == "__main__":
    unittest.main()
