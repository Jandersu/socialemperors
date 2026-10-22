"""Verify denser textures retain exact game geometry and fixed-point matrices."""

from pathlib import Path
import struct
import unittest

from swf_hd_art import encode_matrix, read_matrix, upgrade_shape_bitmap_fill
from swf_localization import localize_swf
from test_swf_localization import flattened_tags


class HdSwfArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes()
        cls.source = dict(
            (struct.unpack_from('<H', payload)[0], payload)
            for code, payload in flattened_tags(cls.original)
            if code in (2, 22, 32, 83)
        )

    def test_only_three_known_fill_matrices_change_without_altering_geometry(self):
        # These byte offsets were inspected in the original game. Checking both
        # sides of each MATRIX covers every bound, edge, line, and other fill.
        expected = {32: (13, 21, 31), 33: (24, 33, 31), 221: (24, 34, 220)}
        localized = localize_swf(self.original)
        shapes = dict(
            (struct.unpack_from('<H', payload)[0], payload)
            for code, payload in flattened_tags(localized)
            if code in (2, 22, 32, 83)
        )
        changed = set()
        for shape_id, source in self.source.items():
            translated = shapes[shape_id]
            if source == translated:
                continue
            changed.add(shape_id)
            start, source_end, bitmap_id = expected[shape_id]
            self.assertEqual(struct.unpack_from('<H', source, start - 2)[0], bitmap_id)
            before, original_end = read_matrix(source, start)
            after, translated_end = read_matrix(translated, start)
            self.assertEqual(original_end, source_end)
            self.assertEqual(source[:start], translated[:start])
            self.assertEqual(source[source_end:], translated[translated_end:])
            self.assertEqual(tuple(value * 4 for value in after[:4]), before[:4])
            self.assertEqual(after[4:], before[4:])
            # Multiplying pixel dimensions by four and dividing the mapping by
            # four yields exactly the same painted extent in stage coordinates.
            logical_width, logical_height = (63, 68) if bitmap_id == 31 else (118, 33)
            self.assertEqual(after[0] * logical_width * 4, before[0] * logical_width)
            self.assertEqual(after[1] * logical_height * 4, before[1] * logical_height)
        self.assertEqual(changed, set(expected))

    def test_matrix_writer_round_trips_fixed_point_skew_and_translation(self):
        for matrix in (
            (65536, 65536, 0, 0, 0, 0),
            (327680, 327680, 0, 0, -1940, -1680),
            (16384, -16384, -24576, 49152, -1073741824, 1073741823),
        ):
            with self.subTest(matrix=matrix):
                encoded = encode_matrix(matrix)
                result, end = read_matrix(encoded)
                self.assertEqual(result, matrix)
                self.assertEqual(end, len(encoded))

    def test_unknown_shapes_stay_identical_and_changed_source_is_rejected(self):
        unknown = next(payload for shape_id, payload in self.source.items() if shape_id not in (32, 33, 221))
        self.assertIs(upgrade_shape_bitmap_fill(unknown, 2), unknown)
        damaged = bytearray(self.source[32])
        damaged[11:13] = struct.pack('<H', 220)
        with self.assertRaisesRegex(ValueError, 'Unexpected original HD bitmap fill'):
            upgrade_shape_bitmap_fill(bytes(damaged), 2)
        with self.assertRaisesRegex(ValueError, 'supported DefineShape'):
            upgrade_shape_bitmap_fill(self.source[32], 46)
        with self.assertRaisesRegex(ValueError, 'exceeds its signed field'):
            encode_matrix((1 << 31, 65536, 0, 0, 0, 0))


if __name__ == '__main__':
    unittest.main()
