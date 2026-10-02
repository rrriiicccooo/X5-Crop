"""Sorted-coordinate indexing preserves the original binary64 distance rule."""
import math
import random
import struct
from types import SimpleNamespace
from unittest import TestCase

from x5crop.detection.photo_geometry.transition_tracking import _coordinate_window, _unique_nearest


class TransitionWindowExactnessTest(TestCase):
    def assert_equivalent(self, coordinate, limit, values):
        points = [SimpleNamespace(coordinate=value) for value in sorted(values) if math.isfinite(value)]
        expected = [i for i,p in enumerate(points) if abs(p.coordinate-coordinate) <= limit]
        actual = [i for i in _coordinate_window(points, coordinate, limit)
                  if abs(points[i].coordinate-coordinate) <= limit]
        self.assertEqual(actual, expected)

    def test_radius_expands_before_cancelling_endpoint_arithmetic(self):
        coordinate = 2.
        limit = math.nextafter(2., 0.)
        accepted = 3*2.**-54
        self.assertEqual(abs(accepted-coordinate), limit)
        self.assertLess(accepted, math.nextafter(coordinate-limit, -math.inf))
        self.assert_equivalent(coordinate, limit, [accepted, coordinate, 4.])

    def test_extremes_subnormals_duplicates_and_infinite_radius(self):
        values = [0., -0., math.ulp(0.), -math.ulp(0.), 2.**-1022, -2.**-1022,
                  1., -1., 2.**53, -2.**53, math.nextafter(math.inf,0.), math.nextafter(-math.inf,0.)]
        for coordinate in values:
            for limit in (0., math.ulp(0.), 1., 2.**53, math.nextafter(math.inf,0.), math.inf):
                self.assert_equivalent(coordinate, limit, values+[coordinate,coordinate])
        self.assertEqual(list(_coordinate_window([], 0., 1.)), [])

    def test_random_binary64_endpoints_match_full_scan(self):
        rng = random.Random(20261002)
        def finite():
            while True:
                value = struct.unpack('>d', rng.getrandbits(64).to_bytes(8,'big'))[0]
                if math.isfinite(value): return value
        for _ in range(1200):
            coordinate, limit = finite(), abs(finite())
            values = [finite(), coordinate, coordinate]
            for endpoint in (coordinate-limit, coordinate+limit):
                if math.isfinite(endpoint):
                    values.append(endpoint)
                    for direction in (-math.inf, math.inf):
                        point = endpoint
                        for _ in range(4):
                            point = math.nextafter(point, direction)
                            values.append(point)
            self.assert_equivalent(coordinate, limit, values)

    def test_polarity_connected_points_and_ties_match_full_scan(self):
        rng = random.Random(441)
        for _ in range(150):
            points = sorted([SimpleNamespace(coordinate=float(rng.randrange(-20,21)), polarity=rng.choice((-1,1)))
                             for _ in range(100)], key=lambda p:p.coordinate)
            connected = set(rng.sample(range(len(points)), 20))
            coordinate, limit = float(rng.randrange(-20,21)), float(rng.randrange(0,10))
            for direct in (False,True):
                def distances(indices):
                    return [(distance,i) for i in indices if i not in connected
                            and (direct or points[i].polarity==1)
                            and (distance:=abs(points[i].coordinate-coordinate))<=limit]
                expected=distances(range(len(points)))
                actual=distances(_coordinate_window(points,coordinate,limit))
                self.assertEqual(actual,expected)
                self.assertEqual(_unique_nearest(actual,.5),_unique_nearest(expected,.5))
