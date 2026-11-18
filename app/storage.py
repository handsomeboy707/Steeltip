"""Repository implementations. Offline JSON is a demo adapter, not a DBMS substitute."""
import copy
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

FIELDS = {
 'players': ['id','name','email','archived','provenance'],
 'tournaments': ['id','name','start_date','archived'],
 'divisions': ['id','tournament_id','name','cap','tolerance','rule_version'],
 'registrations': ['id','player_id','division_id','declared_rating'],
 'matches': ['id','division_id','player1_id','player2_id'],
 'legs': ['id','match_id','number','accepted_revision','accepted_number'],
 'revisions': ['id','leg_id','number','digest','accepted_by','created_at'],
 'results': ['id','leg_id','revision_id','player_id','points','darts','busts','eligible','winner'],
 'snapshots': ['id','revision_id','player_id','cap','tolerance','rule_version','rating','breached'],
 'reviews': ['id','revision_id','player_id','status','note','reviewed_by','reviewed_at'],
 'users': ['id','username','password_hash','role'],
 'sessions': ['id','user_id','expires_at'],
 'audits': ['id','user_id','action','entity_id','details','created_at']
}

class Conflict(ValueError): pass

class DemoRelational:
    mode = 'offline'
    def __init__(self,path=None):
        self.path=Path(path) if path else None
        self.lock=threading.RLock()
        self.data=json.loads(self.path.read_text()) if self.path and self.path.exists() else {t:[] for t in FIELDS}
    def rows(self,table,**where):
        with self.lock: return copy.deepcopy([r for r in self.data[table] if all(r.get(k)==v for k,v in where.items())])
    def one(self,table,**where):
        rows=self.rows(table,**where)
        if not rows: raise ValueError(table+' record not found')
        return rows[0]
    def insert(self,table,row):
        if self.rows(table,id=row['id']): raise Conflict('Duplicate identifier')
        self.data[table].append(copy.deepcopy(row))
    def update(self,table,record_id,changes):
        row=next((r for r in self.data[table] if r['id']==record_id),None)
        if not row: raise ValueError('Record not found')
        row.update(copy.deepcopy(changes))
    def delete(self,table,record_id): self.data[table]=[r for r in self.data[table] if r['id']!=record_id]
    def flush(self):
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp'); temp.write_text(json.dumps(self.data)); temp.replace(self.path)
    @contextmanager
    def transaction(self,leg_id=None):
        with self.lock:
            before=copy.deepcopy(self.data)
            try: yield self; self.flush()
            except Exception: self.data=before; raise

class DemoDocuments:
    def __init__(self,path=None):
        self.path=Path(path) if path else None; self.lock=threading.RLock()
        self.data=json.loads(self.path.read_text()) if self.path and self.path.exists() else {'drafts':{},'revisions':{}}
    def flush(self):
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp'); temp.write_text(json.dumps(self.data)); temp.replace(self.path)
    def get(self,collection,key):
        with self.lock: return copy.deepcopy(self.data[collection].get(key))
    def all(self,collection):
        with self.lock: return copy.deepcopy(list(self.data[collection].values()))
    def insert(self,collection,doc):
        with self.lock:
            if self.get(collection,doc['_id']): raise Conflict('Duplicate document ID')
            if collection=='revisions' and any(x['leg_id']==doc['leg_id'] and x['revision']==doc['revision']
                                               for x in self.data[collection].values()):
                raise Conflict('This leg revision already has immutable evidence')
            self.data[collection][doc['_id']]=copy.deepcopy(doc); self.flush()
    def change_draft(self,key,version,changes):
        with self.lock:
            doc=self.get('drafts',key)
            if not doc or doc['version']!=version or doc['state']!='draft': raise Conflict('Stale or frozen draft; reload')
            doc.update(changes); doc['version']+=1
            self.data['drafts'][key]=doc; self.flush(); return copy.deepcopy(doc)
    def delete_draft(self,key,version):
        with self.lock:
            doc=self.get('drafts',key)
            if not doc or doc['state']!='draft' or doc['version']!=version: raise Conflict('Cannot delete a stale or frozen draft')
            del self.data['drafts'][key]; self.flush()
    def aggregate(self,ids): return aggregate_locally([d for d in self.all('revisions') if d['_id'] in ids])

def aggregate_locally(docs):
    totals={}
    for d in docs:
        if d['status']!='completed': continue
        for v in d['derived']['replay']:
            row=totals.setdefault(v['player_id'],dict(player_id=v['player_id'],points=0,darts=0,busts=0,legs=set()))
            row['points']+=v['points']; row['darts']+=v['darts']; row['busts']+=int(v['bust']); row['legs'].add(d['leg_id'])
    return [dict(r,legs=len(r['legs'])) for _,r in sorted(totals.items())]

class MariaRelational:
    mode='live'
    def __init__(self): self.local=threading.local()
    def connect(self):
        import pymysql
        return pymysql.connect(host=os.getenv('SQL_HOST','mariadb'),port=int(os.getenv('SQL_PORT','3306')),
          user=os.getenv('SQL_USER','steeltip_app'),password=os.environ['SQL_PASSWORD'],
          database='steeltip',charset='utf8mb4',autocommit=False,cursorclass=pymysql.cursors.DictCursor,
          connect_timeout=5,read_timeout=20,write_timeout=20)
    def execute(self,sql,args=(),read=False):
        connection=getattr(self.local,'connection',None); owned=connection is None
        if owned: connection=self.connect()
        try:
            with connection.cursor() as c:
                c.execute(sql,args); result=list(c.fetchall()) if read else c.rowcount
            if owned: connection.commit()
            return result
        except Exception:
            if owned: connection.rollback()
            raise
        finally:
            if owned: connection.close()
    def rows(self,table,**where):
        if table not in FIELDS or any(k not in FIELDS[table] for k in where): raise ValueError('Invalid table/column')
        clause=' AND '.join('`'+k+'`=%s' for k in where)
        return self.execute('SELECT * FROM `'+table+'`'+(' WHERE '+clause if clause else ''),tuple(where.values()),True)
    def one(self,table,**where):
        rows=self.rows(table,**where)
        if not rows: raise ValueError(table+' record not found')
        return rows[0]
    def insert(self,table,row):
        if table not in FIELDS or any(k not in FIELDS[table] for k in row): raise ValueError('Invalid insert columns')
        self.execute('INSERT INTO `'+table+'` ('+','.join('`'+k+'`' for k in row)+') VALUES ('+','.join(['%s']*len(row))+')',tuple(row.values()))
    def update(self,table,record_id,changes):
        if table not in FIELDS or any(k not in FIELDS[table] or k=='id' for k in changes): raise ValueError('Invalid update columns')
        self.execute('UPDATE `'+table+'` SET '+','.join('`'+k+'`=%s' for k in changes)+' WHERE id=%s',(*changes.values(),record_id))
    def delete(self,table,record_id):
        if table not in FIELDS: raise ValueError('Invalid table')
        self.execute('DELETE FROM `'+table+'` WHERE id=%s',(record_id,))
    @contextmanager
    def transaction(self,leg_id=None):
        if getattr(self.local,'connection',None): raise RuntimeError('Nested transaction unsupported')
        c=self.connect(); self.local.connection=c
        try:
            if leg_id: self.execute('SELECT id FROM legs WHERE id=%s FOR UPDATE',(leg_id,),True)
            yield self; c.commit()
        except Exception: c.rollback(); raise
        finally: self.local.connection=None; c.close()

def pipeline(ids):
    return [{'$match':{'_id':{'$in':ids},'status':'completed'}},{'$unwind':'$derived.replay'},
      {'$group':{'_id':'$derived.replay.player_id','points':{'$sum':'$derived.replay.points'},
        'darts':{'$sum':'$derived.replay.darts'},'busts':{'$sum':{'$cond':['$derived.replay.bust',1,0]}},
        'legs':{'$addToSet':'$leg_id'}}},
      {'$project':{'_id':0,'player_id':'$_id','points':1,'darts':1,'busts':1,'legs':{'$size':'$legs'}}},
      {'$sort':{'player_id':1}}]

def summary_pipeline(ids):
    """Matched materialised-summary workload for a fairer SQL/Mongo benchmark."""
    return [{'$match':{'_id':{'$in':ids},'status':'completed'}},
      {'$unwind':'$derived.results'}, {'$match':{'derived.results.eligible':True}},
      {'$group':{'_id':'$derived.results.player_id',
        'points':{'$sum':'$derived.results.points'},'darts':{'$sum':'$derived.results.darts'},
        'busts':{'$sum':'$derived.results.busts'},'legs':{'$sum':1}}},
      {'$project':{'_id':0,'player_id':'$_id','points':1,'darts':1,'busts':1,'legs':1}},
      {'$sort':{'player_id':1}}]

class MongoDocuments:
    def __init__(self):
        from pymongo import MongoClient
        self.db=MongoClient(os.environ['MONGO_URI'],serverSelectionTimeoutMS=5000)['steeltip']
    def get(self,collection,key): return self.db[collection].find_one({'_id':key})
    def all(self,collection): return list(self.db[collection].find())
    def insert(self,collection,doc):
        from pymongo.errors import DuplicateKeyError
        try: self.db[collection].insert_one(copy.deepcopy(doc))
        except DuplicateKeyError as e: raise Conflict('Duplicate document or leg revision') from e
    def change_draft(self,key,version,changes):
        from pymongo import ReturnDocument
        row=self.db.drafts.find_one_and_update({'_id':key,'version':version,'state':'draft'},
          {'$set':changes,'$inc':{'version':1}},return_document=ReturnDocument.AFTER)
        if not row: raise Conflict('Stale or frozen draft; reload')
        return row
    def delete_draft(self,key,version):
        if self.db.drafts.delete_one({'_id':key,'version':version,'state':'draft'}).deleted_count!=1:
            raise Conflict('Cannot delete a stale or frozen draft')
    def aggregate(self,ids): return list(self.db.revisions.aggregate(pipeline(ids)))
