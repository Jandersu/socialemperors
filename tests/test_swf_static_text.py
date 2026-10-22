"""Verify text-only changes in the real embedded SWF font records."""

import json
from pathlib import Path
import unittest

from swf_localization import decode_swf, iter_tags
from swf_static_text import build_font_maps, localize_static_text, read_static_text


class StaticSwfTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        body, offset = decode_swf(Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes())
        cls.fonts = build_font_maps(body)
        cls.payloads = {}
        def visit(stream):
            for code, payload, _ in iter_tags(stream):
                if code == 11:
                    cls.payloads[int.from_bytes(payload[:2], 'little')] = payload
                elif code == 39:
                    visit(payload[4:])
        visit(body[offset:])
        cls.catalog = json.loads(Path('config/locales/pt-BR-static.json').read_text())

    def test_actual_build_and_assist_labels_translate_with_existing_fonts(self):
        for character_id, expected in ((781, 'CONSTRUIR'), (3370, 'AJUDAR!')):
            with self.subTest(character_id=character_id):
                source = self.payloads[character_id]
                translated = localize_static_text(source, self.fonts, self.catalog)
                source_header, _, _, original = read_static_text(source, self.fonts)
                translated_header, _, _, records = read_static_text(translated, self.fonts)
                self.assertEqual(source[:source_header], translated[:translated_header])
                self.assertEqual(records[0]['text'], expected)
                self.assertEqual(records[0]['font_id'], original[0]['font_id'])
                self.assertLessEqual(records[0]['height'], original[0]['height'])
                self.assertLessEqual(sum(a for _, a in records[0]['glyphs']), sum(a for _, a in original[0]['glyphs']))

    def test_unchanged_run_does_not_inherit_size_or_position_from_changed_run(self):
        source = self.payloads[9]
        original = read_static_text(source, self.fonts)[-1]
        self.assertFalse(original[1]['flags'] & 8)  # The original inherits its size.
        catalog = {original[0]['text']: 'Esta frase longa deve caber na largura original sem afetar a próxima linha.'}
        result = localize_static_text(source, self.fonts, catalog)
        records = read_static_text(result, self.fonts)[-1]
        self.assertLess(records[0]['height'], original[0]['height'])
        for key in ('text', 'height', 'font_id', 'x', 'y', 'glyphs'):
            self.assertEqual(records[1][key], original[1][key], key)

    def test_uncatalogued_or_unavailable_glyphs_leave_asset_identical(self):
        for payload in self.payloads.values():
            self.assertEqual(localize_static_text(payload, self.fonts, {}), payload)
        source = self.payloads[781]
        self.assertEqual(localize_static_text(source, self.fonts, {'BUILD': '\U0001f3f0'}), source)


if __name__ == '__main__':
    unittest.main()
