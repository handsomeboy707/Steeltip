import json
import tempfile
import unittest
from pathlib import Path
from app.native_setup import fresh_settings,save_settings,ensure_sql_schema,ROOT
from app.storage import FIELDS

class Cursor:
    def __init__(self,tables=(),different_columns=False,view=True):
        self.tables=set(tables);self.different_columns=different_columns;self.view=view;self.executed=[];self.answer=[]
    def execute(self,sql,args=()):
        self.executed.append((sql,args))
        if "TABLE_TYPE='BASE TABLE'" in sql:self.answer=[(t,) for t in self.tables]
        elif 'information_schema.COLUMNS' in sql:self.answer=[(f,) for f in FIELDS[args[0]] if not(self.different_columns and f=='id')]
        elif 'information_schema.VIEWS' in sql:self.answer=[('accepted_results',)] if self.view else []
        else:self.answer=[]
    def fetchall(self):return self.answer
    def fetchone(self):return self.answer[0] if self.answer else None

class NativeSetupTests(unittest.TestCase):
    def test_generated_settings_are_local_and_not_demo_passwords(self):
        a=fresh_settings();b=fresh_settings()
        self.assertEqual(a['environment']['SQL_HOST'],'127.0.0.1')
        self.assertIn('@127.0.0.1:27017/steeltip',a['environment']['MONGO_URI'])
        self.assertNotEqual(a['sql_user'],b['sql_user']);self.assertNotEqual(a['environment']['SQL_PASSWORD'],b['environment']['SQL_PASSWORD'])
        self.assertGreaterEqual(len(a['environment']['ORGANISER_PASSWORD']),12)
        self.assertNotIn('MARIADB_ROOT_PASSWORD',a['environment'])
    def test_settings_roundtrip_retains_passwords(self):
        parent=(ROOT/'runtime'/'native-setup-tests').resolve();parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as d:
            self.assertTrue(Path(d).resolve().is_relative_to(parent))
            p=Path(d)/'runtime'/'native-settings.json';s=fresh_settings();save_settings(s,p)
            self.assertEqual(json.loads(p.read_text()),s)
    def test_fresh_sql_schema_uses_supplied_ddl(self):
        c=Cursor();ensure_sql_schema(c)
        self.assertTrue(any('CREATE TABLE players' in x for x,_ in c.executed))
        self.assertTrue(any('fk_accepted_revision' in x for x,_ in c.executed))
        self.assertFalse(any('DROP ' in x for x,_ in c.executed))
    def test_existing_complete_schema_is_retained(self):
        c=Cursor(FIELDS);ensure_sql_schema(c)
        self.assertFalse(any('CREATE TABLE' in x for x,_ in c.executed))
        self.assertFalse(any('ALTER TABLE' in x for x,_ in c.executed))
    def test_partial_schema_is_not_overwritten(self):
        c=Cursor(['players'])
        with self.assertRaises(RuntimeError):ensure_sql_schema(c)
        self.assertFalse(any('CREATE TABLE' in x for x,_ in c.executed))
    def test_mismatched_columns_are_not_overwritten(self):
        c=Cursor(FIELDS,different_columns=True)
        with self.assertRaises(RuntimeError):ensure_sql_schema(c)
        self.assertFalse(any('ALTER TABLE' in x for x,_ in c.executed))
    def test_missing_view_is_created(self):
        c=Cursor(FIELDS,view=False);ensure_sql_schema(c)
        self.assertTrue(any(x.startswith('CREATE VIEW accepted_results') for x,_ in c.executed))
    def test_native_mongo_schema_keeps_immutable_privileges(self):
        s=json.loads((ROOT/'mongo'/'validators.json').read_text())
        self.assertEqual(set(s['collections']),{'drafts','revisions'})
        for c in s['collections'].values():
            self.assertEqual(c['validationLevel'],'strict');self.assertEqual(c['validationAction'],'error')
        privileges=next(p for p in s['role']['privileges'] if p['resource']['collection']=='revisions')
        self.assertEqual(set(privileges['actions']),{'find','insert','listIndexes'})

if __name__=='__main__':unittest.main()
