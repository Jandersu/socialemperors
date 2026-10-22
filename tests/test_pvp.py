"""Exercise conserved loot, eligibility, replay and interrupted raid recovery."""

from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pvp
from pvp import RaidError, RaidService, RESOURCE_KEYS


def village(userid, *, units=5, level=10):
    return {
        'playerInfo': {'pid': userid, 'map_names': ['Vila ' + userid], 'default_map': 0,
                       'completed_tutorial': 1, 'cash': 123, 'secret': 'private'},
        'maps': [{'level': level, 'race': 'h', 'coins': 1000, 'wood': 500,
                  'food': 200, 'stone': 9,
                  'items': [[512, index, 0, 0, 0, 0] for index in range(units)]}],
        'privateState': {'gifts': [], 'strategy': 8},
    }


class RaidServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='socialemperors-pvp-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.database_path = self.path / 'raids.sqlite3'
        self.saved_directory = patch.object(pvp.village_sessions, 'SAVES_DIR', str(self.path))
        self.saved_directory.start()
        self.addCleanup(self.saved_directory.stop)
        self.saves = {'alice': village('alice'), 'bob': village('bob', units=1),
                      'carol': village('carol')}
        self.eligible = set(self.saves)
        self.service = RaidService(self.database_path)
        self.lookup = patch.object(pvp, 'session', self.saves.get)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)
        self.writer = patch.object(pvp, 'save_session', self.persist)
        self.writer.start()
        self.addCleanup(self.writer.stop)
        for userid in self.saves:
            self.persist(userid)
        self.now = 1_000_000

    def persist(self, userid):
        (self.path / (userid + '.json')).write_text(json.dumps(self.saves[userid]), encoding='utf-8')

    def raid(self, attacker='alice', defender='bob', token='a' * 32, now=None):
        return self.service.raid(attacker, defender, self.eligible, token, self.now if now is None else now)

    def overview(self, userid='alice', now=None):
        with patch.object(pvp.time, 'time', return_value=self.now if now is None else now):
            return self.service.overview(userid, self.eligible)

    def rows(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute('SELECT * FROM raids ORDER BY rowid').fetchall()

    def test_victory_conserves_each_resource_and_preserves_units_and_cash(self):
        before = deepcopy(self.saves)
        result = self.raid()
        self.assertTrue(result['won'])
        self.assertEqual(result['loot_percent'], 20)
        self.assertEqual(result['loot'], {'coins': 200, 'wood': 100, 'food': 40, 'stone': 1})
        for key in RESOURCE_KEYS:
            self.assertEqual(sum(self.saves[userid]['maps'][0][key] for userid in ('alice', 'bob')),
                             sum(before[userid]['maps'][0][key] for userid in ('alice', 'bob')))
            self.assertGreaterEqual(self.saves['bob']['maps'][0][key], 0)
        for userid in ('alice', 'bob'):
            self.assertEqual(before[userid]['playerInfo'], self.saves[userid]['playerInfo'])
            self.assertEqual(before[userid]['maps'][0]['items'], self.saves[userid]['maps'][0]['items'])
            self.assertEqual(before[userid]['privateState'], self.saves[userid]['privateState'])
            self.assertEqual(json.loads((self.path / (userid + '.json')).read_text()), self.saves[userid])
        row = self.rows()[0]
        self.assertEqual(row['status'], 'applied')
        self.assertIsNone(row['attacker_after_json'])
        self.assertIsNone(row['defender_after_json'])

    def test_ties_favor_defense_and_losses_transfer_nothing(self):
        before = deepcopy(self.saves)
        result = self.raid(defender='carol')
        self.assertFalse(result['won'])
        self.assertEqual(result['total_loot'], 0)
        self.assertEqual(self.saves, before)
        overview = self.overview('carol')
        self.assertEqual(overview['own']['protected_until'], 0)
        self.assertEqual(next(row for row in overview['ranking'] if row['userid'] == 'carol')['defenses_won'], 1)

    def test_army_uses_configuration_ignores_workers_enemies_and_counts_sheltered_troops(self):
        self.saves['alice']['maps'][0]['items'] = [
            [500], [502], [525], [19], [1, 0, 0, 0, 0, 0, [512]], [29], [999999], [], None,
        ]
        own = self.overview()['own']
        self.assertEqual(own['troop_count'], 1)
        self.assertEqual(own['attack_power'], 165)  # Knight: 10*10 + 5*1 + 60.
        self.assertEqual(own['defense_power'], 510)  # Tower: 10*4 + 5*1 + 300.
        self.assertEqual(own['defenses'], 1)

    def test_only_approved_real_villages_can_participate_and_no_self_attack(self):
        self.eligible.remove('bob')
        with self.assertRaises(RaidError):
            self.raid()
        with self.assertRaises(RaidError):
            self.raid(defender='alice')
        with self.assertRaises(RaidError):
            self.service.raid('alice', 'npc', self.eligible | {'npc'}, 'x' * 32, self.now)
        with self.assertRaises(RaidError):
            self.service.overview('bob', self.eligible)
        self.assertEqual({row['userid'] for row in self.overview()['ranking']}, {'alice', 'carol'})
        self.assertEqual(self.rows(), [])

    def test_tutorial_level_and_combatant_guards_match_overview(self):
        cases = [('attacker tutorial', 'alice', 'tutorial', 0),
                 ('defender tutorial', 'bob', 'tutorial', 0),
                 ('level gap', 'bob', 'level', 16),
                 ('no army', 'alice', 'items', [[500], [502], [525]])]
        for label, userid, field, value in cases:
            with self.subTest(label=label):
                original = deepcopy(self.saves[userid])
                if field == 'tutorial':
                    self.saves[userid]['playerInfo']['completed_tutorial'] = value
                else:
                    self.saves[userid]['maps'][0][field] = value
                rival = next(row for row in self.overview()['rivals'] if row['userid'] == 'bob')
                self.assertFalse(rival['can_attack'])
                with self.assertRaisesRegex(RaidError, __import__('re').escape(rival['blocked_reason'])):
                    self.raid()
                self.saves[userid] = original
        self.saves['bob']['maps'][0]['level'] = 15  # Difference 5 is accepted for level 10.
        self.assertTrue(self.raid()['won'])

    def test_cooldowns_and_defender_protection_are_persistent_and_cover_new_request_ids(self):
        self.raid()
        self.service = RaidService(self.database_path)
        with self.assertRaisesRegex(RaidError, 'aguardar'):
            self.raid(defender='carol', token='b' * 32, now=self.now + 899)
        with self.assertRaisesRegex(RaidError, 'protegida'):
            self.raid(attacker='carol', token='c' * 32, now=self.now + 1)
        with self.assertRaisesRegex(RaidError, '6 horas'):
            self.raid(token='d' * 32, now=self.now + 3600)
        allowed = self.raid(token='e' * 32, now=self.now + 6 * 3600)
        self.assertTrue(allowed['won'])
        self.assertEqual(len(self.rows()), 2)

    def test_duplicate_submission_returns_original_result_without_second_transfer(self):
        original = self.raid()
        balances = deepcopy(self.saves)
        self.assertEqual(self.raid(now=self.now + 10), original)
        self.assertEqual(self.saves, balances)
        self.assertEqual(len(self.rows()), 1)
        with self.assertRaisesRegex(RaidError, 'outra vila'):
            self.raid(defender='carol')

    def test_pending_journal_is_committed_before_first_save_and_recovers_after_partial_write(self):
        original = deepcopy(self.saves)
        calls = []

        def interrupted_write(userid):
            calls.append(userid)
            row = self.rows()[0]
            self.assertEqual(row['status'], 'pending')
            self.assertIsNotNone(row['attacker_after_json'])
            self.assertIsNotNone(row['defender_after_json'])
            if len(calls) == 2:
                raise OSError('simulated disk failure')
            self.persist(userid)

        with patch.object(pvp, 'save_session', side_effect=interrupted_write):
            with self.assertRaisesRegex(OSError, 'simulated'):
                self.raid()
        self.assertEqual(self.rows()[0]['status'], 'pending')
        self.assertNotEqual(json.loads((self.path / 'alice.json').read_text()), original['alice'])
        self.assertEqual(json.loads((self.path / 'bob.json').read_text()), original['bob'])
        # Simulate a new process loading the partially updated JSON saves.
        for userid in self.saves:
            self.saves[userid] = json.loads((self.path / (userid + '.json')).read_text())
        restarted = RaidService(self.database_path)
        self.assertEqual(restarted.recover_pending(), 1)
        self.assertEqual(restarted.recover_pending(), 0)
        expected = deepcopy(original)
        for key, loot in {'coins': 200, 'wood': 100, 'food': 40, 'stone': 1}.items():
            expected['alice']['maps'][0][key] += loot
            expected['bob']['maps'][0][key] -= loot
        self.assertEqual(self.saves, expected)
        self.service = restarted
        self.raid()  # Same submitted request after restart is still idempotent.
        self.assertEqual(self.saves, expected)
        self.assertEqual(len(self.rows()), 1)

    def test_history_ranking_and_public_fields_come_from_applied_ledger(self):
        for index in range(22):
            self.raid(token=str(index).zfill(32), now=self.now + index * 6 * 3600)
        overview = self.overview(now=self.now + 22 * 6 * 3600)
        self.assertEqual(len(overview['history']), 20)
        self.assertEqual(overview['history'][0]['role'], 'attacker')
        self.assertEqual(overview['ranking'][0]['userid'], 'alice')
        self.assertEqual(overview['ranking'][0]['wins'], 22)
        self.assertEqual(overview['ranking'][0]['loot_total'], sum(row['total_loot'] for row in self.service._applied()))
        serialized = json.dumps(overview)
        self.assertNotIn('privateState', serialized)
        self.assertNotIn('secret', serialized)
        self.assertNotIn('cash', serialized)

    def test_directory_sync_failure_retains_journal_for_idempotent_recovery(self):
        with patch.object(pvp, '_sync_saves_directory', side_effect=OSError('directory sync failed')):
            with self.assertRaisesRegex(OSError, 'directory sync'):
                self.raid()
        expected = deepcopy(self.saves)
        row = self.rows()[0]
        self.assertEqual(row['status'], 'pending')
        self.assertIsNotNone(row['attacker_after_json'])
        self.assertEqual(self.service.recover_pending(), 1)
        self.assertEqual(self.saves, expected)
        self.assertEqual(self.raid(), json.loads(self.rows()[0]['result_json']))
        self.assertEqual(self.saves, expected)

    def test_invalid_nonce_and_negative_or_fractional_resources_never_settle(self):
        for token in ('', 'short', '../' + 'x' * 20, 'x' * 129, None):
            with self.subTest(token=token), self.assertRaises(RaidError):
                self.raid(token=token)
        for value in (-1, 1.5, True, None, 'nan'):
            self.saves['bob']['maps'][0]['coins'] = value
            with self.subTest(value=value), self.assertRaises(RaidError):
                self.raid()
        self.assertEqual(self.rows(), [])

    def test_revision_changes_only_for_villages_in_settled_raid(self):
        self.assertEqual(self.service.revision('alice'), '')
        first = self.raid()
        self.assertEqual(self.service.revision('alice'), first['id'])
        self.assertEqual(self.service.revision('bob'), first['id'])
        self.assertEqual(self.service.revision('carol'), '')
        second = self.raid(defender='carol', token='z' * 32, now=self.now + 900)
        self.assertEqual(self.service.revision('alice'), second['id'])
        self.assertEqual(self.service.revision('carol'), second['id'])
        self.assertEqual(self.service.revision('bob'), first['id'])


if __name__ == '__main__':
    unittest.main()
