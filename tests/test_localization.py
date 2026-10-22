"""Check real game translations without changing the legacy simulation data."""

from collections import Counter
import copy
import re
import unittest

from get_game_config import get_game_config, get_name_from_item_id
from localization import (
    DISPLAY_FIELDS, load_catalog, localize_game_config, walk_display_fields,
)


class LocalizationTests(unittest.TestCase):
    def test_complete_desktop_catalog_preserves_substitutions_and_markup(self):
        catalog = load_catalog()
        original = get_game_config()
        for section, fields in DISPLAY_FIELDS.items():
            with self.subTest(section=section):
                for _, key, source in walk_display_fields(original[section], fields):
                    if not source:
                        continue
                    self.assertIn(source, catalog, (section, key, source))
                    translated = catalog[source]
                    self.assertEqual(
                        Counter(re.findall(r'#\d+#', source)),
                        Counter(re.findall(r'#\d+#', translated)),
                        source,
                    )
                    self.assertEqual(
                        Counter(re.findall(r'<[^>]+>', source)),
                        Counter(re.findall(r'<[^>]+>', translated)),
                        source,
                    )
                    if key == 'workers':
                        self.assertEqual(source.count(','), translated.count(','))

    def test_only_presentation_fields_change_and_english_engine_stays_intact(self):
        original = get_game_config()
        localized = get_game_config('pt-BR')
        self.assertIsNot(original, localized)
        self.assertEqual(get_name_from_item_id(1), 'House I')
        self.assertEqual(localized['items'][0]['name'], 'Casa I')
        self.assertEqual(localized['localization_strings'][0]['text'], 'Boas-vindas ao seu império!')
        self.assertEqual(original['localization_strings'][0]['text'], 'Welcome to your Empire!')
        # Replacing text in both copies must produce identical mechanics,
        # technical identifiers, asset paths, array shapes and patch nesting.
        mechanics = []
        for config in (original, localized):
            stripped = copy.deepcopy(config)
            for section, fields in DISPLAY_FIELDS.items():
                for entry, key, _ in walk_display_fields(stripped[section], fields):
                    entry[key] = '<display text>'
            mechanics.append(stripped)
        self.assertEqual(mechanics[0], mechanics[1])

    def test_supported_locale_aliases_and_unknown_mod_text_fall_back(self):
        for alias in ('pt', 'pt-br', 'pt_BR', 'pt-BR'):
            self.assertIs(get_game_config(alias), get_game_config('pt-BR'))
        self.assertIs(get_game_config('unsupported'), get_game_config())
        custom = {'items': [{'name': 'New Mod Unit', 'id': 900000, 'cost': 12}]}
        self.assertEqual(localize_game_config(custom), custom)
        # Localization returns independent data even for new mod fields.
        self.assertIsNot(localize_game_config(custom)['items'], custom['items'])


if __name__ == '__main__':
    unittest.main()
