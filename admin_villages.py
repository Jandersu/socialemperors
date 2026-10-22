"""Audited administration of existing home villages.

The caller must authenticate the administrator and hold the shared village lock.
Recover pending raids and administrative edits before any legacy game mutation.
Each edit journals its complete AFTER save before replacing exactly one JSON
save; recovery replays that snapshot instead of repeating resource arithmetic.
"""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
import uuid

from get_game_config import get_game_config
import sessions
from village_names import VillageNameError, set_village_name


RESOURCE_KEYS = ('coins', 'wood', 'food', 'stone')
RESOURCE_LIMIT = 1_000_000_000
CASH_LIMIT = 1_000_000
EDITABLE_FIELDS = frozenset(('name', *RESOURCE_KEYS, 'cash', 'level', 'tutorial_complete'))
HISTORY_LIMIT = 20


class AdminVillageError(ValueError):
    """An administrative edit the administrator can correct."""


class AdminVillageConflict(AdminVillageError):
    """The village changed after the administrator opened its form."""


def _integer(value, label, minimum=0, maximum=RESOURCE_LIMIT):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise AdminVillageError(f'Informe um número inteiro válido para {label}.')
    if isinstance(value, str) and not re.fullmatch(r'0|[1-9][0-9]*', value):
        raise AdminVillageError(f'Informe um número inteiro válido para {label}.')
    try:
        number = int(value)
    except (ValueError, OverflowError):
        raise AdminVillageError(f'Informe um número inteiro válido para {label}.') from None
    if not minimum <= number <= maximum:
        raise AdminVillageError(f'O valor de {label} deve ficar entre {minimum} e {maximum}.')
    return number


def _reason(value):
    if not isinstance(value, str):
        raise AdminVillageError('Informe o motivo da alteração, com 3 a 200 caracteres.')
    reason = unicodedata.normalize('NFC', value).strip()
    if (not 3 <= len(reason) <= 200
            or any(unicodedata.category(character).startswith('C')
                   or character in '\u2028\u2029' for character in reason)):
        raise AdminVillageError('Informe o motivo da alteração, com 3 a 200 caracteres, sem caracteres de controle.')
    return reason


def _main_map(save):
    if not isinstance(save, dict) or not isinstance(save.get('playerInfo'), dict):
        raise AdminVillageError('Vila não encontrada.')
    player = save['playerInfo']
    maps, names = save.get('maps'), player.get('map_names')
    if not isinstance(maps, list) or not isinstance(names, list):
        raise AdminVillageError('A vila não possui um mapa principal válido.')
    index = _integer(player.get('default_map', 0), 'mapa principal')
    if index >= min(len(maps), len(names)) or not isinstance(maps[index], dict):
        raise AdminVillageError('A vila não possui um mapa principal válido.')
    return index, maps[index]


def _editable_snapshot(save):
    index, town = _main_map(save)
    return {
        'map_index': index,
        'name': save['playerInfo']['map_names'][index],
        'resources': {key: town.get(key, 0) for key in RESOURCE_KEYS},
        'cash': save['playerInfo'].get('cash', 0),
        'level': town.get('level', 1),
        'xp': town.get('xp', 0),
        'tutorial_complete': save['playerInfo'].get('completed_tutorial', 0) == 1,
    }


def _revision(save):
    # Include raw tutorial state and the actual PID as well as every form field.
    # Game collection, raids, rename and level progress invalidate an old form.
    payload = {
        **_editable_snapshot(save),
        'pid': save['playerInfo'].get('pid'),
        'completed_tutorial': save['playerInfo'].get('completed_tutorial', 0),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _sync_saves_directory():
    if os.name != 'posix':
        return
    descriptor = os.open(sessions.SAVES_DIR, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AdminVillageService:
    def __init__(self, database_path):
        self.database_path = str(Path(database_path).expanduser())
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS admin_village_changes (
                    id TEXT PRIMARY KEY,
                    userid TEXT NOT NULL,
                    admin_account_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'applied')),
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    changed_fields_json TEXT NOT NULL,
                    after_snapshot_json TEXT
                );
                CREATE INDEX IF NOT EXISTS admin_village_changes_userid
                    ON admin_village_changes(userid, created_at);
                CREATE INDEX IF NOT EXISTS admin_village_changes_pending
                    ON admin_village_changes(status);
            ''')

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA synchronous = FULL')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _save(userid):
        if not isinstance(userid, str):
            raise AdminVillageError('Vila não encontrada.')
        save = sessions.session(userid)
        if not isinstance(save, dict) or str(save.get('playerInfo', {}).get('pid')) != userid:
            raise AdminVillageError('Vila não encontrada.')
        _main_map(save)
        return save

    @property
    def max_level(self):
        # The legacy level resolver returns the index of the next XP bound.
        # Therefore the final config entry bounds the highest playable level;
        # setting XP to that entry would make get_level_from_xp return zero.
        return len(get_game_config()['levels']) - 1

    def get(self, userid):
        save = self._save(userid)
        return {
            'userid': userid,
            **_editable_snapshot(save),
            'revision': _revision(save),
            'max_level': self.max_level,
        }

    def revision(self, userid):
        return _revision(self._save(userid))

    def change_revision(self, userid):
        """Identify settled admin edits without changing on normal gameplay.

        The full save-field hash above protects edit forms. HUD polling instead
        needs this durable operation ID, so collecting resources does not make
        the player unnecessarily reload their village.
        """
        self._save(userid)
        with self._connection() as connection:
            row = connection.execute('''SELECT id FROM admin_village_changes
                WHERE userid = ? AND status = 'applied'
                ORDER BY rowid DESC LIMIT 1''', (userid,)).fetchone()
        return row['id'] if row else ''

    def history(self, userid, limit=HISTORY_LIMIT):
        self._save(userid)
        limit = _integer(limit, 'limite do histórico', 1, 100)
        with self._connection() as connection:
            rows = connection.execute('''SELECT * FROM admin_village_changes
                WHERE userid = ? ORDER BY rowid DESC LIMIT ?''', (userid, limit)).fetchall()
        return [{
            'id': row['id'], 'userid': row['userid'],
            'admin_account_id': row['admin_account_id'], 'reason': row['reason'],
            'created_at': row['created_at'], 'status': row['status'],
            'before': json.loads(row['before_json']), 'after': json.loads(row['after_json']),
            'changed_fields': json.loads(row['changed_fields_json']),
        } for row in rows]

    def _apply(self, row):
        snapshot = json.loads(row['after_snapshot_json'])
        userid = row['userid']
        save = self._save(userid)
        if str(snapshot.get('playerInfo', {}).get('pid')) != userid:
            raise RuntimeError('Não foi possível recuperar a alteração: vila ausente ou inválida.')
        _main_map(snapshot)
        previous = deepcopy(save)
        save.clear()
        save.update(snapshot)
        try:
            sessions.save_session(userid)
            _sync_saves_directory()
        except Exception:
            # Keep the live save consistent with its pre-edit state until the
            # caller retries recovery. The durable journal remains pending.
            save.clear()
            save.update(previous)
            raise
        with self._connection() as connection:
            connection.execute('''UPDATE admin_village_changes
                SET status = 'applied', after_snapshot_json = NULL
                WHERE id = ? AND status = 'pending' ''', (row['id'],))

    def recover_pending(self):
        """Replay durable AFTER saves before allowing further game mutations."""
        with self._connection() as connection:
            pending = connection.execute('''SELECT * FROM admin_village_changes
                WHERE status = 'pending' ORDER BY rowid''').fetchall()
        for row in pending:
            self._apply(row)
        return len(pending)

    def update(self, userid, values, admin_account_id, expected_revision, reason):
        self.recover_pending()
        save = self._save(userid)
        admin_account_id = _integer(admin_account_id, 'administrador', 1, 2 ** 63 - 1)
        reason = _reason(reason)
        if not isinstance(expected_revision, str) or expected_revision != _revision(save):
            raise AdminVillageConflict('A vila mudou desde que esta tela foi aberta. Confira os valores atuais e tente novamente.')
        if not isinstance(values, dict) or not values or set(values) - EDITABLE_FIELDS:
            raise AdminVillageError('Selecione somente os campos permitidos para editar a vila.')
        after = deepcopy(save)
        _, town = _main_map(after)
        if 'name' in values:
            try:
                set_village_name(after, values['name'])
            except VillageNameError as error:
                raise AdminVillageError(str(error)) from None
        for key in RESOURCE_KEYS:
            if key in values:
                town[key] = _integer(values[key], key)
        if 'cash' in values:
            after['playerInfo']['cash'] = _integer(values['cash'], 'dinheiro', maximum=CASH_LIMIT)
        if 'level' in values:
            level = _integer(values['level'], 'nível', 1, self.max_level)
            levels = get_game_config()['levels']
            minimum_xp = int(levels[level - 1]['exp_required'])
            maximum_xp = int(levels[level]['exp_required']) if level < len(levels) else None
            current_xp = town.get('xp', 0)
            coherent = (type(current_xp) is int and current_xp >= minimum_xp
                        and (maximum_xp is None or current_xp < maximum_xp))
            if town.get('level') != level or not coherent:
                town['xp'] = minimum_xp
            town['level'] = level
        if 'tutorial_complete' in values:
            complete = values['tutorial_complete']
            if type(complete) is bool:
                complete = int(complete)
            else:
                complete = _integer(complete, 'conclusão do tutorial', 0, 1)
            after['playerInfo']['completed_tutorial'] = complete
        before_public, after_public = _editable_snapshot(save), _editable_snapshot(after)
        changed_fields = [key for key in ('name', *RESOURCE_KEYS, 'cash', 'level', 'xp', 'tutorial_complete')
                          if (before_public['resources'][key] != after_public['resources'][key]
                              if key in RESOURCE_KEYS else before_public[key] != after_public[key])]
        if not changed_fields:
            return {**self.get(userid), 'operation_id': None, 'changed_fields': []}
        operation_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute('''INSERT INTO admin_village_changes
                (id, userid, admin_account_id, reason, created_at, status,
                 before_json, after_json, changed_fields_json, after_snapshot_json)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)''', (
                    operation_id, userid, admin_account_id, reason, int(time.time()),
                    json.dumps(before_public, ensure_ascii=False), json.dumps(after_public, ensure_ascii=False),
                    json.dumps(changed_fields), json.dumps(after, ensure_ascii=False),
                ))
            row = connection.execute('SELECT * FROM admin_village_changes WHERE id = ?', (operation_id,)).fetchone()
        self._apply(row)
        return {**self.get(userid), 'operation_id': operation_id, 'changed_fields': changed_fields}
