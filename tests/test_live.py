"""Explicit opt-in: run only in a disposable MariaDB + MongoDB test installation."""
import copy,os,unittest
from uuid import uuid4

@unittest.skipUnless(os.getenv('STEELTIP_LIVE_TESTS')=='1','Set STEELTIP_LIVE_TESTS=1 in an isolated database installation')
class LiveDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.server import create_application
        cls.app=create_application(live=True,seed_data=True)
    def test_live_accepted_aggregate_equality(self): self.assertTrue(self.app.compare()['equal'])
    def test_live_reconciliation(self): self.assertTrue(self.app.reconcile()['ok'])
    def test_document_schema_rejects_invalid_shape(self):
        from pymongo.errors import OperationFailure
        with self.assertRaises(OperationFailure) as error: self.app.d.db.drafts.insert_one({'_id':str(uuid4())})
        self.assertEqual(error.exception.code,121)
    def test_unique_leg_revision_index(self):
        from pymongo.errors import DuplicateKeyError
        row=copy.deepcopy(self.app.d.all('revisions')[0]);row['_id']=str(uuid4())
        with self.assertRaises(DuplicateKeyError): self.app.d.db.revisions.insert_one(row)
    def test_immutable_collection_denies_update(self):
        from pymongo.errors import OperationFailure
        row=self.app.d.all('revisions')[0]
        with self.assertRaises(OperationFailure) as error: self.app.d.db.revisions.update_one({'_id':row['_id']},{'$set':{'digest':row['digest']}})
        self.assertEqual(error.exception.code,13)
    def test_sql_duplicate_registration(self):
        from pymysql import IntegrityError
        row=dict(self.app.r.rows('registrations')[0]);row['id']=str(uuid4())
        with self.assertRaises(IntegrityError):
            with self.app.r.transaction(): self.app.r.insert('registrations',row)
