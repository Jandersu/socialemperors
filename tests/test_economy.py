"""Free grants remain once-only across restarts and interrupted save writes."""

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import economy
from economy import EconomyError, EconomyService, DAILY_INTERVAL_SECONDS, MAX_CASH


class EconomyServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='socialemperors-treasury-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.database = self.path / 'treasury.sqlite3'
        self.saves = {
            userid: {'playerInfo': {'pid': userid, 'cash': 0},
                     'maps': [{'coins': 250, 'wood': 870, 'food': 650, 'stone': 250, 'items': [[512]]}],
                     'privateState': {'completedMissions': [1]}}
            for userid in ('alice', 'bob')
        }
        self.now = 1_000_000
        for name, value in (('session', self.saves.get), ('save_session', self.persist)):
            patcher = patch.object(economy, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(economy.village_sessions, 'SAVES_DIR', str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(economy.time, 'time', lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = EconomyService(self.database)
        for userid in self.saves:
            self.persist(userid)

    def persist(self, userid):
        (self.path / (userid + '.json')).write_text(json.dumps(self.saves[userid]), encoding='utf-8')

    def rows(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute('SELECT * FROM treasury_claims ORDER BY rowid').fetchall()

    def test_initial_and_daily_are_independent_and_modify_only_cash(self):
        before = deepcopy(self.saves)
        overview = self.service.overview('alice')
        self.assertTrue(overview['initial_available'])
        self.assertTrue(overview['can_claim'])
        self.assertEqual(overview['next_claim_at'], 0)
        self.assertEqual(overview['balance'], 0)
        self.assertEqual(self.rows(), [])  # GET never grants anything.
        first = self.service.claim('alice', 'initial')
        second = self.service.claim('alice', 'daily')
        self.assertEqual((first['amount'], second['amount']), (500, 100))
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 600)
        expected = deepcopy(before)
        expected['alice']['playerInfo']['cash'] = 600
        self.assertEqual(self.saves, expected)
        self.assertEqual(json.loads((self.path / 'alice.json').read_text()), expected['alice'])
        overview = self.service.overview('alice')
        self.assertFalse(overview['initial_available'])
        self.assertFalse(overview['can_claim'])
        self.assertEqual(overview['next_claim_at'], self.now + DAILY_INTERVAL_SECONDS)
        self.assertEqual(overview['history'], [second, first])
        self.assertTrue(all(row['status'] == 'applied' and row['after_json'] is None for row in self.rows()))

    def test_daily_can_precede_initial_and_bonuses_do_not_accumulate(self):
        self.service.claim('alice', 'daily')
        self.service.claim('alice', 'initial')
        self.now += 10 * DAILY_INTERVAL_SECONDS
        result = self.service.claim('alice', 'daily')
        self.assertEqual(result['amount'], 100)
        self.assertEqual(result['balance'], 700)

    def test_double_submission_restart_and_clock_rollback_do_not_duplicate(self):
        self.service.claim('alice', 'initial')
        self.service.claim('alice', 'daily')
        self.service = EconomyService(self.database)
        with self.assertRaisesRegex(EconomyError, 'inicial'):
            self.service.claim('alice', 'initial')
        with self.assertRaisesRegex(EconomyError, '24 horas'):
            self.service.claim('alice', 'daily')
        self.now -= 100
        with self.assertRaises(EconomyError):
            self.service.claim('alice', 'daily')
        self.now = 1_000_000 + DAILY_INTERVAL_SECONDS - 1
        with self.assertRaises(EconomyError):
            self.service.claim('alice', 'daily')
        self.now += 1
        self.assertEqual(self.service.claim('alice', 'daily')['balance'], 700)
        self.assertEqual(len(self.rows()), 3)

    def test_limit_rejects_entire_grant_without_using_eligibility(self):
        self.saves['alice']['playerInfo']['cash'] = MAX_CASH - 499
        with self.assertRaisesRegex(EconomyError, 'limite'):
            self.service.claim('alice', 'initial')
        self.assertEqual(self.rows(), [])
        self.assertTrue(self.service.overview('alice')['initial_available'])
        self.saves['alice']['playerInfo']['cash'] = str(MAX_CASH - 500)
        self.assertEqual(self.service.claim('alice', 'initial')['balance'], MAX_CASH)
        with self.assertRaises(EconomyError):
            self.service.claim('alice', 'daily')
        self.assertEqual(len(self.rows()), 1)

    def test_invalid_balances_village_kind_and_configuration_are_rejected(self):
        for cash in (-1, 2.5, True, None, 'nan'):
            self.saves['alice']['playerInfo']['cash'] = cash
            with self.subTest(cash=cash), self.assertRaises(EconomyError):
                self.service.claim('alice', 'daily')
        self.saves['alice']['playerInfo']['cash'] = 0
        for kind in ('', 'purchase', None):
            with self.assertRaises(EconomyError):
                self.service.claim('alice', kind)
        with self.assertRaises(EconomyError):
            self.service.claim('unknown', 'initial')
        for value in (0, -1, True, 1.5, MAX_CASH + 1):
            with self.assertRaises(ValueError):
                EconomyService(self.database, initial_bonus=value)
        self.assertEqual(self.rows(), [])

    def test_pending_ledger_recovers_failed_save_without_second_credit(self):
        before = deepcopy(self.saves)

        def interrupted(userid):
            self.assertEqual(self.rows()[0]['status'], 'pending')
            self.assertIsNotNone(self.rows()[0]['after_json'])
            raise OSError('interrupted save')

        with patch.object(economy, 'save_session', interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.service.claim('alice', 'initial')
        self.assertEqual(self.rows()[0]['status'], 'pending')
        self.assertEqual(json.loads((self.path / 'alice.json').read_text()), before['alice'])
        for userid in self.saves:
            self.saves[userid] = json.loads((self.path / (userid + '.json')).read_text())
        restarted = EconomyService(self.database)
        self.assertEqual(restarted.recover_pending(), 1)
        self.assertEqual(restarted.recover_pending(), 0)
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 500)
        with self.assertRaises(EconomyError):
            restarted.claim('alice', 'initial')
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 500)
        self.assertEqual(len(self.rows()), 1)
        self.assertIsNone(self.rows()[0]['after_json'])

    def test_directory_sync_failure_remains_recoverable(self):
        with patch.object(economy, '_sync_saves_directory', side_effect=OSError('directory sync')):
            with self.assertRaises(OSError):
                self.service.claim('alice', 'daily')
        self.assertEqual(self.rows()[0]['status'], 'pending')
        self.assertEqual(self.service.recover_pending(), 1)
        self.assertEqual(self.saves['alice']['playerInfo']['cash'], 100)
        with self.assertRaises(EconomyError):
            self.service.claim('alice', 'daily')
        self.assertEqual(len(self.rows()), 1)

    def test_history_and_revision_are_per_village_and_bounded(self):
        self.assertEqual(self.service.revision('alice'), '')
        self.service.claim('bob', 'initial')
        for index in range(22):
            self.now += DAILY_INTERVAL_SECONDS
            latest = self.service.claim('alice', 'daily')
        self.assertEqual(self.service.revision('alice'), latest['id'])
        self.assertNotEqual(self.service.revision('bob'), latest['id'])
        history = self.service.overview('alice')['history']
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0], latest)
        self.assertNotIn('maps', json.dumps(history))


if __name__ == '__main__':
    unittest.main()
