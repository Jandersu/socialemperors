"""Free private-server cash grants, recorded before modifying a village save.

The caller holds the shared village lock and recovers every pending service
before allowing legacy commands or administrative changes to touch the save.
No amount, balance, clock or eligibility is supplied by the game client.
"""

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from sessions import session, save_session
import sessions as village_sessions


DAILY_INTERVAL_SECONDS = 24 * 60 * 60
MAX_CASH = 1_000_000
HISTORY_LIMIT = 20


class EconomyError(ValueError):
    """A grant which the player cannot claim at this time."""


def _balance(save):
    value = save['playerInfo'].get('cash', 0)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise EconomyError('O saldo de dinheiro da vila está inválido. Contate o administrador.')
    try:
        result = int(value)
    except ValueError:
        raise EconomyError('O saldo de dinheiro da vila está inválido. Contate o administrador.') from None
    if result < 0:
        raise EconomyError('O saldo de dinheiro da vila está inválido. Contate o administrador.')
    return result


def _sync_saves_directory():
    if os.name != 'posix':
        return
    descriptor = os.open(village_sessions.SAVES_DIR, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class EconomyService:
    def __init__(self, database_path, initial_bonus=500, daily_reward=100):
        for name, value in (('initial_bonus', initial_bonus), ('daily_reward', daily_reward)):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_CASH:
                raise ValueError(f'{name} deve ser um inteiro entre 1 e {MAX_CASH}.')
        self.initial_bonus = initial_bonus
        self.daily_reward = daily_reward
        self.database_path = str(Path(database_path).expanduser())
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS treasury_claims (
                    id TEXT PRIMARY KEY,
                    userid TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('initial', 'daily')),
                    claimed_at INTEGER NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'applied')),
                    result_json TEXT NOT NULL,
                    after_json TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS treasury_initial_once
                    ON treasury_claims(userid) WHERE kind = 'initial';
                CREATE INDEX IF NOT EXISTS treasury_user_time
                    ON treasury_claims(userid, claimed_at);
                CREATE INDEX IF NOT EXISTS treasury_pending ON treasury_claims(status);
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
        save = session(userid)
        if save is None or str(save['playerInfo']['pid']) != userid:
            raise EconomyError('Sua vila não foi encontrada. Entre novamente ou contate o administrador.')
        return save

    def _apply(self, row):
        userid = row['userid']
        snapshot = json.loads(row['after_json'])
        save = session(userid)
        if save is None or str(snapshot['playerInfo']['pid']) != userid:
            raise RuntimeError('Não foi possível recuperar o resgate: vila ausente ou inválida.')
        save.clear()
        save.update(snapshot)
        save_session(userid)
        _sync_saves_directory()
        with self._connection() as connection:
            connection.execute('''UPDATE treasury_claims SET status = 'applied', after_json = NULL
                WHERE id = ? AND status = 'pending' ''', (row['id'],))

    def recover_pending(self):
        """Apply durable AFTER snapshots, including grants interrupted mid-write."""
        with self._connection() as connection:
            rows = connection.execute('''SELECT * FROM treasury_claims WHERE status = 'pending'
                ORDER BY claimed_at, rowid''').fetchall()
        for row in rows:
            self._apply(row)
        return len(rows)

    def revision(self, userid):
        with self._connection() as connection:
            row = connection.execute('''SELECT id FROM treasury_claims
                WHERE userid = ? AND status = 'applied' ORDER BY rowid DESC LIMIT 1''', (str(userid),)).fetchone()
        return row['id'] if row else ''

    def overview(self, userid):
        userid = str(userid)
        save = self._save(userid)
        balance = _balance(save)
        now = int(time.time())
        with self._connection() as connection:
            initial = connection.execute('''SELECT 1 FROM treasury_claims
                WHERE userid = ? AND kind = 'initial' ''', (userid,)).fetchone()
            daily = connection.execute('''SELECT MAX(claimed_at) AS claimed_at FROM treasury_claims
                WHERE userid = ? AND kind = 'daily' ''', (userid,)).fetchone()['claimed_at']
            history = connection.execute('''SELECT result_json FROM treasury_claims
                WHERE userid = ? AND status = 'applied' ORDER BY claimed_at DESC, rowid DESC LIMIT ?''',
                (userid, HISTORY_LIMIT)).fetchall()
        next_claim_at = daily + DAILY_INTERVAL_SECONDS if daily is not None else 0
        return {
            'balance': balance,
            'initial_bonus': self.initial_bonus,
            'initial_available': initial is None,
            'daily_reward': self.daily_reward,
            'can_claim': next_claim_at <= now,
            'next_claim_at': next_claim_at,
            'history': [json.loads(row['result_json']) for row in history],
            'max_balance': MAX_CASH,
        }

    def claim(self, userid, kind='daily'):
        self.recover_pending()
        userid = str(userid)
        if kind not in ('initial', 'daily'):
            raise EconomyError('Escolha um resgate válido.')
        save = self._save(userid)
        now = int(time.time())
        amount = self.initial_bonus if kind == 'initial' else self.daily_reward
        with self._connection() as connection:
            # The shared village lock serializes all services. This transaction
            # additionally makes the eligibility check and ledger insert atomic.
            connection.execute('BEGIN IMMEDIATE')
            if kind == 'initial':
                previous = connection.execute('''SELECT 1 FROM treasury_claims
                    WHERE userid = ? AND kind = 'initial' ''', (userid,)).fetchone()
                if previous:
                    raise EconomyError('Você já resgatou o bônus inicial desta vila.')
            else:
                previous = connection.execute('''SELECT MAX(claimed_at) AS claimed_at
                    FROM treasury_claims WHERE userid = ? AND kind = 'daily' ''', (userid,)).fetchone()['claimed_at']
                if previous is not None and now < previous + DAILY_INTERVAL_SECONDS:
                    raise EconomyError('O resgate diário fica disponível a cada 24 horas após o último resgate.')
            balance = _balance(save)
            if balance + amount > MAX_CASH:
                raise EconomyError('Use parte do seu dinheiro antes de resgatar: o limite de saldo é 1.000.000.')
            snapshot = deepcopy(save)
            snapshot['playerInfo']['cash'] = balance + amount
            result = {
                'id': uuid.uuid4().hex, 'kind': kind, 'amount': amount,
                'balance': balance + amount, 'claimed_at': now,
            }
            connection.execute('''INSERT INTO treasury_claims
                (id, userid, kind, claimed_at, amount, status, result_json, after_json)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)''', (
                    result['id'], userid, kind, now, amount,
                    json.dumps(result, ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False),
                ))
            row = connection.execute('SELECT * FROM treasury_claims WHERE id = ?', (result['id'],)).fetchone()
        self._apply(row)
        return result
