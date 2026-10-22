"""Portuguese display text for the legacy client, independent of engine data.

Only explicitly listed presentation fields are localized. Image filenames,
script names, resource codes, unit IDs, prices and other rules remain intact.
Uncatalogued text from a new mod falls back to its original wording.
"""

import copy
import json
from pathlib import Path

from bundle import CONFIG_DIR


DISPLAY_FIELDS = {
    'localization_strings': frozenset({'text'}),
    'categories': frozenset({'name'}),
    'items': frozenset({'name', 'achievement_desc'}),
    'missions': frozenset({'title', 'description', 'hint'}),
    'levels': frozenset({'name'}),
    'honor_levels': frozenset({'rank'}),
    'neighbor_assists': frozenset({'task', 'action', 'notification'}),
    'findable_items': frozenset({'title', 'description'}),
    'magics': frozenset({'name', 'description'}),
    'social_items': frozenset({'workers'}),
    'tournament_type': frozenset({'name'}),
    'level_up_tips': frozenset({'text'}),
}


def normalize_locale(language):
    return 'pt-BR' if str(language).lower().replace('_', '-') in {'pt', 'pt-br'} else 'en'


def load_catalog(language='pt-BR'):
    """Load source-text keys so config patches retain their original IDs."""
    if normalize_locale(language) != 'pt-BR':
        return {}
    catalog = {}
    # Specific item names take precedence over short generic UI wording.
    filenames = (
        'pt-BR-core.json', 'pt-BR-interface.json', 'pt-BR-extended.json',
        'pt-BR-collections.json', 'pt-BR-missions.json',
        'pt-BR-auxiliary.json', 'pt-BR-items.json',
    )
    for filename in filenames:
        with (Path(CONFIG_DIR) / 'locales' / filename).open(encoding='utf-8') as stream:
            catalog.update(json.load(stream))
    return catalog


def walk_display_fields(value, fields):
    """Yield writable text fields, including the legacy nested patch arrays."""
    if isinstance(value, list):
        for item in value:
            yield from walk_display_fields(item, fields)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in fields and isinstance(item, str):
                yield value, key, item
            elif isinstance(item, (dict, list)):
                yield from walk_display_fields(item, fields)


def localize_game_config(config, language='pt-BR'):
    localized = copy.deepcopy(config)
    catalog = load_catalog(language)
    for section, fields in DISPLAY_FIELDS.items():
        for entry, key, source in walk_display_fields(localized.get(section), fields):
            entry[key] = catalog.get(source, source)
    return localized
