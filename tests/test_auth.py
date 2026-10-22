import sqlite3
from contextlib import closing
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from werkzeug.exceptions import BadRequest
from werkzeug.security import check_password_hash

import auth
from auth import AccountError, AccountStore, csrf_token, validate_csrf


class AccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = Path(self.directory.name) / "private" / "accounts.sqlite3"
        self.store = AccountStore(self.database_path)

    def create(self, suffix="one", **kwargs):
        return self.store.create_account(
            "Player " + suffix, suffix + "@example.com", "secret-password", **kwargs
        )

    def test_pending_accounts_persist_and_passwords_are_hashed(self):
        account = self.store.create_account("  Ana Silva  ", "  ANA@Example.COM ", "secret-password")
        self.assertEqual(account["name"], "Ana Silva")
        self.assertEqual(account["email"], "ana@example.com")
        self.assertEqual(account["status"], "pending")
        self.assertFalse(account["is_admin"])
        self.assertIsNone(account["village_id"])
        self.assertNotIn("password_hash", account)
        reopened = AccountStore(self.database_path)
        self.assertEqual(reopened.get(account["id"]), account)
        self.assertEqual(reopened.authenticate("ANA@example.com", "secret-password"), account)
        self.assertIsNone(reopened.authenticate(account["email"], "wrong-password"))
        self.assertIsNone(reopened.authenticate("nobody@example.com", "secret-password"))
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            stored_hash = connection.execute("SELECT password_hash FROM accounts").fetchone()[0]
        self.assertNotEqual(stored_hash, "secret-password")
        self.assertTrue(check_password_hash(stored_hash, "secret-password"))

    def test_email_uniqueness_is_case_insensitive(self):
        self.create()
        with self.assertRaisesRegex(AccountError, "Já existe"):
            self.store.create_account("Another", " ONE@EXAMPLE.COM ", "another-secret")
        self.assertEqual(len(self.store.list_accounts()), 1)

    def test_account_input_validation(self):
        invalid = [
            ("A", "player@example.com", "secret-password"),
            ("A" * 61, "player@example.com", "secret-password"),
            ("Player", "invalid", "secret-password"),
            ("Player", "bad name@example.com", "secret-password"),
            ("Player", "x" * 250 + "@example.com", "secret-password"),
            ("Player", "player@example.com", "short"),
            ("Player", "player@example.com", "x" * 129),
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(AccountError):
                self.store.create_account(*arguments)
        self.assertEqual(self.store.list_accounts(), [])

    def test_sql_metacharacters_do_not_modify_other_accounts(self):
        account = self.store.create_account("O'Connor", "o'connor@example.com", "secret-password")
        self.assertIsNone(self.store.authenticate("' OR 1=1 --", "secret-password"))
        self.assertEqual(self.store.get(account["id"])["name"], "O'Connor")

    def test_approval_and_rejection_are_visible_to_other_store_instances(self):
        account = self.create()
        other = AccountStore(self.database_path)
        self.assertEqual(self.store.set_status(account["id"], "approved")["status"], "approved")
        self.assertEqual(other.get(account["id"])["status"], "approved")
        self.assertEqual(other.set_status(account["id"], "rejected")["status"], "rejected")
        self.assertEqual(self.store.get(account["id"])["status"], "rejected")
        with self.assertRaises(AccountError):
            self.store.set_status(account["id"], "invalid")
        with self.assertRaises(AccountError):
            self.store.set_status(9999, "approved")
        self.assertIsNone(self.store.get(9999))
        self.assertIsNone(self.store.get(None))

    def test_pending_accounts_are_listed_first_without_secrets(self):
        approved = self.create("approved", status="approved")
        pending = self.create("pending")
        rejected = self.create("rejected", status="rejected")
        accounts = self.store.list_accounts()
        self.assertEqual([item["id"] for item in accounts], [pending["id"], approved["id"], rejected["id"]])
        self.assertTrue(all("password_hash" not in item for item in accounts))

    def test_admin_creation_is_explicit_and_admin_cannot_be_deactivated(self):
        self.assertFalse(self.create()["is_admin"])
        admin = self.store.create_admin("Admin", "admin@example.com", "admin-password", village_id="42")
        self.assertTrue(admin["is_admin"])
        self.assertEqual(admin["status"], "approved")
        self.assertEqual(admin["village_id"], "42")
        for status in ("pending", "rejected"):
            with self.subTest(status=status), self.assertRaisesRegex(AccountError, "administrador"):
                self.store.set_status(admin["id"], status)
        self.assertEqual(self.store.set_status(admin["id"], "approved"), admin)
        with self.assertRaises(AccountError):
            self.create("invalid-admin", is_admin=True)

    def test_villages_are_unique_and_binding_is_idempotent(self):
        first = self.create("first")
        second = self.create("second")
        bound = self.store.bind_village(first["id"], 42)
        self.assertEqual(bound["village_id"], "42")
        self.assertEqual(self.store.bind_village(first["id"], "42"), bound)
        with self.assertRaisesRegex(AccountError, "outra conta"):
            self.store.bind_village(second["id"], "42")
        with self.assertRaisesRegex(AccountError, "já possui"):
            self.store.bind_village(first["id"], "43")
        self.assertIsNone(self.store.get(second["id"])["village_id"])
        self.assertEqual(AccountStore(self.database_path).get(first["id"]), bound)

    def test_failed_admin_village_assignment_does_not_leave_an_account(self):
        first = self.create()
        self.store.bind_village(first["id"], "42")
        with self.assertRaises(AccountError):
            self.store.create_admin("Admin", "admin@example.com", "admin-password", village_id="42")
        self.assertEqual(len(self.store.list_accounts()), 1)

    def test_concurrent_initialization_and_binding_preserve_village_ownership(self):
        database_path = Path(self.directory.name) / "parallel" / "accounts.sqlite3"
        ready = threading.Barrier(2)

        def bind_from_worker(index):
            store = AccountStore(database_path)
            account = store.create_account(
                "Player " + str(index), "player{}@example.com".format(index), "secret-password"
            )
            ready.wait(timeout=5)
            try:
                return store.bind_village(account["id"], "shared-village")
            except AccountError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(bind_from_worker, range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)
        accounts = AccountStore(database_path).list_accounts()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(sum(item["village_id"] == "shared-village" for item in accounts), 1)

    def test_login_throttling_is_persistent_and_expires(self):
        with patch("auth.time.time", return_value=1000):
            for _ in range(auth.LOGIN_EMAIL_LIMIT):
                self.store.check_login_allowed("player@example.com", "192.0.2.1")
                self.store.record_login_failure("player@example.com", "192.0.2.1")
            other = AccountStore(self.database_path)
            with self.assertRaisesRegex(AccountError, "Muitas tentativas"):
                other.check_login_allowed("PLAYER@example.com", "192.0.2.2")
            other.check_login_allowed("other@example.com", "192.0.2.1")
        with patch("auth.time.time", return_value=1000 + auth.LOGIN_WINDOW_SECONDS + 1):
            self.store.check_login_allowed("player@example.com", "192.0.2.1")
            with closing(sqlite3.connect(self.database_path)) as connection, connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM login_throttles").fetchone()[0], 0)

    def test_ip_throttling_cannot_be_reset_by_a_successful_login(self):
        for index in range(auth.LOGIN_IP_LIMIT):
            self.store.record_login_failure("player{}@example.com".format(index), "192.0.2.1")
        self.store.clear_login_failures("player0@example.com", "192.0.2.1")
        with self.assertRaises(AccountError):
            self.store.check_login_allowed("new@example.com", "192.0.2.1")
        self.store.check_login_allowed("new@example.com", "192.0.2.2")

    def test_success_clears_account_counter_and_throttle_rows_are_bounded(self):
        with patch("auth.MAX_LOGIN_BUCKETS", 6):
            for index in range(8):
                self.store.record_login_failure("player{}@example.com".format(index), "192.0.2.{}".format(index))
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertLessEqual(connection.execute("SELECT COUNT(*) FROM login_throttles").fetchone()[0], 6)
        for _ in range(auth.LOGIN_EMAIL_LIMIT):
            self.store.record_login_failure("reset@example.com", "198.51.100.1")
        self.store.clear_login_failures("reset@example.com", "198.51.100.1")
        self.store.check_login_allowed("reset@example.com", "198.51.100.1")


class CsrfTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test-only-secret"

    def test_generated_token_is_stable_within_the_session(self):
        with self.app.test_request_context():
            token = csrf_token()
            self.assertGreaterEqual(len(token), 32)
            self.assertEqual(csrf_token(), token)

    def test_valid_token_is_accepted_and_missing_or_mismatched_tokens_are_rejected(self):
        for form_token, session_token, valid in (
            ("matching-token", "matching-token", True),
            (None, "matching-token", False),
            ("mismatched-token", "matching-token", False),
            ("token-inválido", "matching-token", False),
            ("matching-token", None, False),
        ):
            with self.subTest(form_token=form_token, session_token=session_token):
                data = {"csrf_token": form_token} if form_token is not None else {}
                with self.app.test_request_context(method="POST", data=data):
                    if session_token is not None:
                        auth.session["_csrf_token"] = session_token
                    if valid:
                        self.assertIsNone(validate_csrf())
                    else:
                        with self.assertRaises(BadRequest):
                            validate_csrf()


if __name__ == "__main__":
    unittest.main()
