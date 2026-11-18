import unittest
from unittest.mock import MagicMock
from app.reset_password import reset_account
from app.service import password_hash
from app.api import dispatch
from app.diagnostics import inspect_databases
from app.storage import DemoRelational, DemoDocuments
from app.service import Application


class RecoveryTests(unittest.TestCase):
    def test_hash_reset_revokes_sessions_and_audits_in_one_commit(self):
        c = MagicMock(); cur = c.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = ('user-id',)
        reset_account(c, 'organiser', 'a-new-private-password')
        calls = cur.execute.call_args_list
        encoded = calls[1].args[1][0]
        self.assertEqual(encoded, password_hash('a-new-private-password', encoded.split(':')[0]))
        self.assertIn('DELETE FROM sessions', calls[2].args[0])
        self.assertIn('INSERT INTO audits', calls[3].args[0])
        self.assertNotIn('a-new-private-password', str(calls))
        c.commit.assert_called_once(); c.rollback.assert_not_called()

    def test_missing_user_rolls_back_without_insert(self):
        c = MagicMock(); cur = c.cursor.return_value.__enter__.return_value; cur.fetchone.return_value = None
        with self.assertRaisesRegex(ValueError, 'not found'): reset_account(c, 'missing', 'a-new-private-password')
        c.rollback.assert_called_once(); c.commit.assert_not_called()
        self.assertEqual(cur.execute.call_count, 1)

    def test_failed_update_rolls_back(self):
        c = MagicMock(); cur = c.cursor.return_value.__enter__.return_value; cur.fetchone.return_value = ('user-id',)
        cur.execute.side_effect = [None, RuntimeError('denied')]
        with self.assertRaisesRegex(RuntimeError, 'denied'): reset_account(c, 'organiser', 'a-new-private-password')
        c.rollback.assert_called_once(); c.commit.assert_not_called()

    def test_short_password_does_not_open_transaction(self):
        c = MagicMock()
        with self.assertRaises(ValueError): reset_account(c, 'organiser', 'short')
        c.begin.assert_not_called()


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.app = Application(DemoRelational(), DemoDocuments())
        for role in ('organiser','viewer'):
            self.app.add_user(role, 'a-long-demo-password', role)

    def test_offline_never_claims_live_databases(self):
        result = inspect_databases(self.app)
        self.assertFalse(result['verified_live']); self.assertEqual(result['mode'], 'offline')

    def test_diagnostics_denies_viewer(self):
        token = self.app.login('viewer','a-long-demo-password')['token']
        with self.assertRaises(PermissionError): dispatch(self.app,'GET','/api/diagnostics',{},token)

    def test_diagnostics_requires_session(self):
        with self.assertRaises(PermissionError): dispatch(self.app,'GET','/api/diagnostics',{},'')

    def test_organiser_observes_demo_status(self):
        token = self.app.login('organiser','a-long-demo-password')['token']
        self.assertFalse(dispatch(self.app,'GET','/api/diagnostics',{},token)['verified_live'])


if __name__ == '__main__': unittest.main()
