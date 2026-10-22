"""Administrative edits preserve unrelated save data and survive interruptions."""

from contextlib import closing, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import admin_villages
from admin_villages import AdminVillageConflict, AdminVillageError, AdminVillageService
from get_game_config import get_game_config, get_level_from_xp
import sessions


def village(userid):
    return {
        'playerInfo': {
            'pid': userid, 'name': 'Nome da conta preservado', 'cash': 8,
            'default_map': '1', 'map_names': ['Ilha distante', 'Vila principal'],
            'completed_tutorial': 0, 'pic': '/img/profile/1025.png',
        },
        'maps': [
            {'id': 0, 'coins': 91, 'wood': 92, 'food': 93, 'stone': 94,
             'xp': 4, 'level': 1, 'items': [[512, 1, 2]]},
            {'id': 1, 'coins': 250, 'wood': 850, 'food': 700, 'stone': 250,
             'xp': 4, 'level': 1, 'items': [[19, 7, 8]], 'questTimes': [1, 2]},
        ],
        'privateState': {'gifts': [[1, 3]], 'completedMissions': [4], 'inventory': {'5': 3}},
    }


class AdminVillageServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='socialemperors-admin-villages-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.database_path = self.path / 'accounts.sqlite3'
        self.saves = {'alice': village('alice'), 'bob': village('bob')}
        self.service = AdminVillageService(self.database_path)
        for patcher in (
            patch.object(sessions, 'SAVES_DIR', self.directory.name),
            patch.object(sessions, '__saves', self.saves),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        for userid in self.saves:
            sessions.save_session(userid)

    def update(self, values, *, userid='alice', admin_account_id=17,
               expected_revision=None, reason='Ajuste para os amigos'):
        if expected_revision is None:
            expected_revision = self.service.revision(userid)
        return self.service.update(userid, values, admin_account_id, expected_revision, reason)

    def disk(self, userid='alice'):
        return json.loads((self.path / f'{userid}.save.json').read_text(encoding='utf-8'))

    def rows(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute('SELECT * FROM admin_village_changes ORDER BY rowid').fetchall()

    def test_snapshot_shows_only_management_fields_and_revision_tracks_editable_state(self):
        snapshot = self.service.get('alice')
        self.assertEqual(snapshot['userid'], 'alice')
        self.assertEqual(snapshot['name'], 'Vila principal')
        self.assertEqual(snapshot['resources'], {'coins': 250, 'wood': 850, 'food': 700, 'stone': 250})
        self.assertEqual(snapshot['cash'], 8)
        self.assertEqual(snapshot['map_index'], 1)
        self.assertFalse(snapshot['tutorial_complete'])
        self.assertEqual(snapshot['max_level'], len(get_game_config()['levels']) - 1)
        self.assertEqual(snapshot['revision'], self.service.revision('alice'))
        self.assertNotIn('privateState', snapshot)
        self.assertNotIn('playerInfo', snapshot)
        self.saves['alice']['maps'][1]['coins'] += 1
        self.assertNotEqual(snapshot['revision'], self.service.revision('alice'))

    def test_combined_edit_persists_once_preserves_identity_other_island_and_audits_before_after(self):
        before = deepcopy(self.saves)
        with patch.object(sessions, 'save_session', wraps=sessions.save_session) as writer:
            result = self.update({
                'name': '  São José dos Amigos  ', 'coins': '0', 'wood': '1000000000',
                'food': 400, 'stone': 77, 'cash': '1000000', 'level': '4',
                'tutorial_complete': '1',
            })
        writer.assert_called_once_with('alice')
        self.assertEqual(result['name'], 'São José dos Amigos')
        self.assertEqual(result['resources'], {'coins': 0, 'wood': 1_000_000_000, 'food': 400, 'stone': 77})
        self.assertEqual(result['xp'], get_game_config()['levels'][3]['exp_required'])
        self.assertEqual(result['level'], 4)
        self.assertTrue(result['tutorial_complete'])
        self.assertEqual(self.saves['alice']['maps'][0], before['alice']['maps'][0])
        self.assertEqual(self.saves['alice']['maps'][1]['items'], before['alice']['maps'][1]['items'])
        self.assertEqual(self.saves['alice']['privateState'], before['alice']['privateState'])
        self.assertEqual(self.saves['alice']['playerInfo']['name'], before['alice']['playerInfo']['name'])
        self.assertEqual(self.saves['bob'], before['bob'])
        self.assertEqual(self.disk(), self.saves['alice'])
        history = self.service.history('alice')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['id'], result['operation_id'])
        self.assertEqual(history[0]['admin_account_id'], 17)
        self.assertEqual(history[0]['reason'], 'Ajuste para os amigos')
        self.assertEqual(history[0]['before']['cash'], 8)
        self.assertEqual(history[0]['after']['cash'], 1_000_000)
        self.assertEqual(set(history[0]['changed_fields']), {'name', 'coins', 'wood', 'food', 'stone', 'cash', 'level', 'xp', 'tutorial_complete'})
        self.assertEqual(history[0]['status'], 'applied')
        self.assertIsNone(self.rows()[0]['after_snapshot_json'])

    def test_subset_edit_and_unchanged_form_do_not_reset_xp_or_write_a_noop(self):
        self.update({'cash': 20})
        with patch.object(sessions, 'save_session') as writer:
            result = self.update({'level': '1', 'cash': '20'})
        writer.assert_not_called()
        self.assertEqual(result['changed_fields'], [])
        self.assertIsNone(result['operation_id'])
        self.assertEqual(result['xp'], 4)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.saves['alice']['maps'][1]['coins'], 250)

    def test_level_changes_both_directions_and_incoherent_xp_use_config_thresholds(self):
        self.update({'level': 10})
        self.assertEqual(self.service.get('alice')['xp'], get_game_config()['levels'][9]['exp_required'])
        self.update({'level': 2})
        self.assertEqual(self.service.get('alice')['xp'], get_game_config()['levels'][1]['exp_required'])
        self.saves['alice']['maps'][1]['xp'] = 1_000_000
        self.update({'level': 2})
        self.assertEqual(self.service.get('alice')['xp'], 29)
        self.update({'level': self.service.max_level})
        self.assertEqual(self.service.get('alice')['xp'], get_game_config()['levels'][-2]['exp_required'])

    def test_every_offered_level_roundtrips_through_legacy_xp_resolver(self):
        levels = get_game_config()['levels']
        for level in range(1, self.service.max_level + 1):
            with self.subTest(level=level):
                self.assertEqual(get_level_from_xp(levels[level - 1]['exp_required']), level)
        self.assertEqual(get_level_from_xp(levels[-1]['exp_required']), 0)
        self.assertEqual(self.service.max_level, 99)

    def test_invalid_values_never_write_or_create_audit_entries(self):
        before = deepcopy(self.saves)
        bad_values = [
            {'coins': -1}, {'coins': '01'}, {'coins': ' 1'}, {'coins': '+1'},
            {'coins': 1.5}, {'coins': True}, {'coins': '1e3'}, {'coins': '١'},
            {'coins': 1_000_000_001}, {'cash': 1_000_001}, {'cash': '-0'},
            {'level': 0}, {'level': self.service.max_level + 1}, {'level': False},
            {'name': '<b>Vila</b>'}, {'name': 'A'}, {'tutorial_complete': 'true'},
            {'tutorial_complete': 2}, {'xp': 777}, {'userid': 'bob'},
            {'items': []}, {}, [], {'cash': None},
        ]
        with patch.object(sessions, 'save_session') as writer:
            for values in bad_values:
                with self.subTest(values=values), self.assertRaises(AdminVillageError):
                    self.update(values)
            for reason in ('', 'ab', 'A' * 201, None, 'A\x00B'):
                with self.subTest(reason=reason), self.assertRaises(AdminVillageError):
                    self.update({'cash': 9}, reason=reason)
            for admin_id in (0, True, '01', 'bob'):
                with self.subTest(admin_id=admin_id), self.assertRaises(AdminVillageError):
                    self.update({'cash': 9}, admin_account_id=admin_id)
        writer.assert_not_called()
        self.assertEqual(self.saves, before)
        self.assertEqual(self.disk(), before['alice'])
        self.assertEqual(self.rows(), [])

    def test_concurrent_game_resource_xp_name_or_tutorial_changes_reject_stale_form(self):
        for field in ('coins', 'xp', 'name', 'tutorial'):
            revision = self.service.revision('alice')
            if field in ('coins', 'xp'):
                self.saves['alice']['maps'][1][field] += 1
            elif field == 'name':
                self.saves['alice']['playerInfo']['map_names'][1] = 'Novo nome no jogo'
            else:
                self.saves['alice']['playerInfo']['completed_tutorial'] = 1
            with self.subTest(field=field), self.assertRaises(AdminVillageConflict):
                self.update({'cash': 99}, expected_revision=revision)
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 8)
        self.assertEqual(self.rows(), [])

    def test_unknown_or_mismatched_village_cannot_be_edited(self):
        for userid in ('missing', None, 3):
            with self.subTest(userid=userid), self.assertRaises(AdminVillageError):
                self.service.get(userid)
        self.saves['alice']['playerInfo']['pid'] = 'bob'
        with self.assertRaises(AdminVillageError):
            self.service.update('alice', {'cash': 0}, 17, 'revision', 'Motivo válido')
        self.assertEqual(self.rows(), [])

    def test_failed_atomic_replace_rolls_back_memory_and_recovery_replays_durable_after(self):
        before = deepcopy(self.saves['alice'])
        with patch.object(sessions.os, 'replace', side_effect=OSError('disco indisponível')):
            with self.assertRaises(OSError):
                self.update({'cash': 50, 'coins': 900})
        self.assertEqual(self.saves['alice'], before)
        self.assertEqual(self.disk(), before)
        self.assertEqual(self.rows()[0]['status'], 'pending')
        self.assertIsNotNone(self.rows()[0]['after_snapshot_json'])
        restarted = AdminVillageService(self.database_path)
        self.assertEqual(restarted.recover_pending(), 1)
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 50)
        self.assertEqual(self.saves['alice']['maps'][1]['coins'], 900)
        self.assertEqual(self.disk(), self.saves['alice'])
        with patch.object(sessions, 'save_session') as writer:
            self.assertEqual(restarted.recover_pending(), 0)
        writer.assert_not_called()
        self.assertEqual(len(restarted.history('alice')), 1)
        self.assertIsNone(self.rows()[0]['after_snapshot_json'])

    def test_update_recovers_pending_before_comparing_revision_or_running_next_edit(self):
        old_revision = self.service.revision('alice')
        with patch.object(sessions, 'save_session', side_effect=OSError('interrompido')):
            with self.assertRaises(OSError):
                self.update({'coins': 800}, expected_revision=old_revision)
        with self.assertRaises(AdminVillageConflict):
            self.update({'coins': 250, 'cash': 100}, expected_revision=old_revision)
        self.assertEqual(self.saves['alice']['maps'][1]['coins'], 800)
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 8)
        self.assertEqual(self.disk(), self.saves['alice'])
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]['status'], 'applied')

    def test_journal_failure_leaves_save_and_memory_untouched(self):
        before = deepcopy(self.saves['alice'])
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute('''CREATE TRIGGER reject_admin_changes
                BEFORE INSERT ON admin_village_changes
                BEGIN SELECT RAISE(ABORT, 'journal unavailable'); END''')
            connection.commit()
        with patch.object(sessions, 'save_session') as writer:
            with self.assertRaises(sqlite3.IntegrityError):
                self.update({'cash': 100})
        writer.assert_not_called()
        self.assertEqual(self.saves['alice'], before)
        self.assertEqual(self.disk(), before)
        self.assertEqual(self.rows(), [])

    def test_directory_sync_failure_keeps_pending_journal_recoverable_after_disk_replace(self):
        before = deepcopy(self.saves['alice'])
        with patch.object(admin_villages, '_sync_saves_directory', side_effect=OSError('sync falhou')):
            with self.assertRaises(OSError):
                self.update({'cash': 30})
        self.assertEqual(self.saves['alice'], before)
        self.assertEqual(self.disk()['playerInfo']['cash'], 30)
        self.assertEqual(self.rows()[0]['status'], 'pending')
        # Simulate process restart reading the already-replaced JSON file.
        self.saves['alice'].clear()
        self.saves['alice'].update(self.disk())
        self.assertEqual(self.service.recover_pending(), 1)
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 30)
        self.assertEqual(self.disk(), self.saves['alice'])
        self.assertEqual(len(self.rows()), 1)

    def test_history_is_scoped_newest_first_limited_and_tutorial_accepts_booleans(self):
        self.update({'tutorial_complete': True})
        self.update({'tutorial_complete': False}, reason='Voltar ao tutorial')
        self.update({'cash': 15}, userid='bob')
        history = self.service.history('alice', 1)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['reason'], 'Voltar ao tutorial')
        self.assertFalse(history[0]['after']['tutorial_complete'])
        self.assertTrue(history[0]['before']['tutorial_complete'])
        self.assertEqual(len(self.service.history('alice')), 2)
        self.assertEqual(len(self.service.history('bob')), 1)

    def test_change_revision_identifies_only_applied_admin_edits_not_normal_gameplay(self):
        self.assertEqual(self.service.change_revision('alice'), '')
        first = self.update({'cash': 20})
        self.assertEqual(self.service.change_revision('alice'), first['operation_id'])
        self.assertEqual(self.service.change_revision('bob'), '')
        form_revision = self.service.revision('alice')
        self.saves['alice']['maps'][1]['coins'] += 10
        self.assertNotEqual(form_revision, self.service.revision('alice'))
        self.assertEqual(self.service.change_revision('alice'), first['operation_id'])
        with patch.object(sessions, 'save_session', side_effect=OSError('interrompido')):
            with self.assertRaises(OSError):
                self.update({'cash': 30})
        self.assertEqual(self.service.change_revision('alice'), first['operation_id'])
        self.service.recover_pending()
        self.assertEqual(self.service.change_revision('alice'), self.service.history('alice')[0]['id'])
        self.assertNotEqual(self.service.change_revision('alice'), first['operation_id'])


if __name__ == '__main__':
    unittest.main()
