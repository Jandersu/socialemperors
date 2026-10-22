import sys
import os

# Bundled data (extracted to a temp dir)

TMP_BUNDLED_DIR = sys._MEIPASS if getattr(sys, 'frozen', None) else "."

ASSETS_DIR = os.path.join(TMP_BUNDLED_DIR, "assets")
STUB_DIR = os.path.join(TMP_BUNDLED_DIR, "stub")
TEMPLATES_DIR = os.path.join(TMP_BUNDLED_DIR, "templates")
VILLAGES_DIR = os.path.join(TMP_BUNDLED_DIR, "villages")
QUESTS_DIR = os.path.join(VILLAGES_DIR, "quests")
CONFIG_DIR = os.path.join(TMP_BUNDLED_DIR, "config")
CONFIG_PATCH_DIR = os.path.join(CONFIG_DIR, "patch")

# Not bundled data (next to server EXE)

BASE_DIR = "."

MODS_DIR = os.path.join(BASE_DIR, "mods")
SAVES_DIR = os.environ.get('SOCIAL_EMPIRES_SAVES_DIR') or (
    os.path.join(os.environ['SOCIAL_EMPIRES_DATA_DIR'], 'saves')
    if os.environ.get('SOCIAL_EMPIRES_DATA_DIR') else os.path.join(BASE_DIR, 'saves')
)
