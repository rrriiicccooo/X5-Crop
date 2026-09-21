from copy import deepcopy
import unittest

import numpy as np

from tools.regression.gold_boundary_features import (
    boundary_segments, feature_rows, inventory, sample_profiles, source_groups,
)


def geometry():
    def line(identity, points, role):
        return dict(line_id=identity, points_raw=points, role=role, review_basis='directly_visible')
    return dict(
        coordinate_system={'continuous_coordinates': 'raw_tiff_raster_pixel_centers'},
        shared_edges=[line('T', [[0, 31.5], [199, 31.5]], 'short_low'),
                      line('B', [[0, 159.5], [199, 159.5]], 'short_high')],
        boundary_pool=[line('L', [[31.5, 0], [31.5, 199]], 'long_boundary'),
                       line('R', [[159.5, 0], [159.5, 199]], 'long_boundary')],
        slots=[dict(ordinal=1, slot_kind='image', reference_geometry=dict(
            kind='boundary_pair', start_boundary_id='L', end_boundary_id='R'))])


class GoldBoundaryFeaturesContractTest(unittest.TestCase):
    def test_geometric_spans_and_inward_roles_are_raw_and_frame_bound(self):
        spans = boundary_segments(geometry(), 'HW')
        self.assertEqual([s['role'] for s in spans], ['top', 'bottom', 'start', 'end'])
        np.testing.assert_allclose([s['inward_normal'] for s in spans], [[0, 1], [0, -1], [1, 0], [-1, 0]])
        self.assertTrue(all(s['physical_frame_key'] == ('L', 'R') for s in spans))
        blank = geometry()
        blank['slots'][0]['reference_geometry'] = {'kind': 'not_applicable'}
        self.assertEqual(boundary_segments(blank, 'HW'), [])

    def test_constant_pixels_do_not_create_contact_or_texture(self):
        raw = np.full((200, 200, 3), 12000, dtype=np.uint16)
        profiles, texture, radius, _ = sample_profiles(raw, boundary_segments(geometry(), 'H')[0])
        for row in feature_rows(profiles, texture, radius):
            self.assertTrue(all(row['valid']))
            self.assertTrue(all(v == 0 for v in row['values']['signed_gray_change']))
            self.assertTrue(all(v == 0 for v in row['values']['inside_normal_texture']))

    def test_sustained_step_and_isolated_band_have_different_persistence(self):
        segment = boundary_segments(geometry(), 'H')[0]
        results = []
        for band in (False, True):
            raw = np.full((200, 200, 3), 10000, dtype=np.uint16)
            raw[32:36 if band else 200] = 40000
            profiles, texture, radius, _ = sample_profiles(raw, segment)
            row = next(r for r in feature_rows(profiles, texture, radius)
                       if r['offset_inward_px'] == 0 and r['window_px'] == 4)
            results.append(row['values']['persistent_same_polarity'])
        self.assertTrue(all(v == 1 for v in results[0]))
        self.assertTrue(all(v == 0 for v in results[1]))

    def test_color_feature_retains_nearly_isoluminant_change(self):
        raw = np.full((200, 200, 3), 20000, dtype=np.uint16)
        raw[32:, :, 0] += 10000
        raw[32:, :, 1] -= 2973
        profiles, texture, radius, _ = sample_profiles(raw, boundary_segments(geometry(), 'H')[0])
        row = next(r for r in feature_rows(profiles, texture, radius)
                   if r['offset_inward_px'] == 0 and r['window_px'] == 4)
        self.assertLess(max(map(abs, row['values']['signed_gray_change'])), 1e-5)
        self.assertGreater(min(row['values']['opponent_color_change']), .1)

    def test_tiff_exterior_is_missing_not_clamped_or_a_negative(self):
        segment = boundary_segments(geometry(), 'H')[0]
        segment['first'] = segment['first'] - [0, 35]
        segment['last'] = segment['last'] - [0, 35]
        profiles, texture, radius, _ = sample_profiles(np.zeros((200, 200, 3), np.uint16), segment)
        row = next(r for r in feature_rows(profiles, texture, radius)
                   if r['offset_inward_px'] == 0 and r['window_px'] == 4)
        self.assertFalse(any(row['valid']))
        self.assertTrue(all(v is None for v in row['values']['outside_gray']))

    def test_mirrored_transposed_raw_geometry_preserves_measurements(self):
        raw = np.full((200, 200, 3), 10000, dtype=np.uint16)
        raw[32:] = 30000
        original = geometry()
        transformed = deepcopy(original)
        for line in transformed['shared_edges'] + transformed['boundary_pool']:
            line['points_raw'] = [[199 - y, x] for x, y in line['points_raw']]
        first = sample_profiles(raw, boundary_segments(original, 'H')[0])
        second = sample_profiles(np.rot90(raw, k=3), boundary_segments(transformed, 'H')[0])
        for left, right in zip(first[:3], second[:3], strict=True):
            np.testing.assert_allclose(left, right)

    def test_native_tiff_byte_order_does_not_change_numeric_pixels(self):
        raw = np.full((200, 200, 3), 12345, dtype=np.uint16)
        segment = boundary_segments(geometry(), 'H')[0]
        for left, right in zip(sample_profiles(raw, segment), sample_profiles(raw.astype('>u2'), segment), strict=True):
            np.testing.assert_allclose(left, right)

    def test_all_same_source_tasks_and_visibility_classes_stay_together(self):
        source = geometry()
        source['boundary_pool'][0]['review_basis'] = 'human_width_estimate'
        source['boundary_pool'][1]['review_basis'] = 'visible_content_limit'
        rows = tuple(dict(source_sha256='a' * 64, sample_id=f'S{i}', count=i, confirmed_geometry=source) for i in (1, 2))
        groups = source_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0]['count'], 2)
        data = inventory(groups)
        self.assertEqual(data['physical_boundary_review_bases']['W'], {'human_width_estimate': 1, 'visible_content_limit': 1})
        self.assertEqual(len(data['source_groups']), 1)
        changed = deepcopy(rows)
        changed[0]['confirmed_geometry']['shared_edges'][0]['points_raw'][0][1] += 1
        # deepcopy preserves shared references; make the second geometry independent.
        changed[1]['confirmed_geometry'] = geometry()
        with self.assertRaisesRegex(ValueError, 'physical geometry'):
            source_groups(changed)


if __name__ == '__main__':
    unittest.main()
