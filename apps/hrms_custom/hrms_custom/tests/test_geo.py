import unittest

from hrms_custom.utils.geo import Geofence, haversine_meters, resolve_geofence, validate_coordinates

# Ahmedabad HQ and a branch ~5 km away (fixtures chosen from real coordinates).
HQ = Geofence("HQ - Ahmedabad", 23.0225, 72.5714, 200)
BRANCH = Geofence("Branch - SG Highway", 23.0395, 72.5300, 300)


class TestHaversine(unittest.TestCase):
	def test_zero_distance(self):
		self.assertEqual(haversine_meters(23.0225, 72.5714, 23.0225, 72.5714), 0)

	def test_known_distance_ahmedabad_to_mumbai(self):
		# Great-circle distance is ~441 km; allow 1% tolerance.
		distance = haversine_meters(23.0225, 72.5714, 19.0760, 72.8777)
		self.assertAlmostEqual(distance, 439_500, delta=4_500)

	def test_one_thousandth_degree_latitude_is_about_111m(self):
		self.assertAlmostEqual(haversine_meters(23.0, 72.0, 23.001, 72.0), 111.2, delta=0.5)

	def test_antipodal_points_do_not_raise(self):
		self.assertGreater(haversine_meters(0, 0, 0, 180), 20_000_000)


class TestResolveGeofence(unittest.TestCase):
	def test_no_geofences(self):
		self.assertIsNone(resolve_geofence(23.0, 72.0, []))

	def test_inside_single_geofence(self):
		match = resolve_geofence(23.0230, 72.5714, [HQ])  # ~55 m north
		self.assertTrue(match.is_within)
		self.assertEqual(match.geofence, HQ)
		self.assertLess(match.distance_meters, 60)

	def test_just_outside_radius(self):
		match = resolve_geofence(23.0245, 72.5714, [HQ])  # ~222 m north, radius 200
		self.assertFalse(match.is_within)
		self.assertEqual(match.geofence, HQ)

	def test_outside_all_returns_nearest(self):
		match = resolve_geofence(23.0300, 72.5714, [BRANCH, HQ])
		self.assertFalse(match.is_within)
		self.assertEqual(match.geofence, HQ)

	def test_inside_second_of_many(self):
		match = resolve_geofence(23.0396, 72.5301, [HQ, BRANCH])
		self.assertTrue(match.is_within)
		self.assertEqual(match.geofence, BRANCH)

	def test_prefers_containing_fence_over_closer_center(self):
		small = Geofence("Small", 23.0, 72.0, 10)
		large = Geofence("Large", 23.0005, 72.0, 500)
		# 20 m from Small's center (outside its 10 m radius), ~35 m from Large's center (inside).
		match = resolve_geofence(23.00018, 72.0, [small, large])
		self.assertTrue(match.is_within)
		self.assertEqual(match.geofence, large)


class TestValidateCoordinates(unittest.TestCase):
	def test_valid(self):
		validate_coordinates(23.0, 72.0)

	def test_invalid(self):
		for lat, lng in ((91, 0), (-91, 0), (0, 181), (0, -181), (float("nan"), 0), (0, float("inf"))):
			with self.subTest(lat=lat, lng=lng), self.assertRaises(ValueError):
				validate_coordinates(lat, lng)
