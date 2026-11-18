import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from .scoring import score, breached, digest, RULE
from .storage import Conflict

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='microseconds')
def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),240000).hex()
def permitted(user,*roles):
    if not user or user['role'] not in roles: raise PermissionError('This operation requires '+', '.join(roles))
def decimal_value(value):
    try: d=Decimal(str(value))
    except InvalidOperation: raise ValueError('A numeric value is required')
    if not d.is_finite() or d < 0 or d > Decimal('99999.9999') or d.as_tuple().exponent < -4:
        raise ValueError('Use a nonnegative number with at most four decimal places')
    return format(d,'f')
def name_value(value,maximum=120):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum: raise ValueError('A valid name is required')
    return value.strip()

class Application:
    def __init__(self,relational,documents): self.r=relational; self.d=documents
    def audit(self,user,action,entity,details=None):
        self.r.insert('audits',dict(id=uid(),user_id=user['id'],action=action,entity_id=entity,
            details=json.dumps(details or {},default=str),created_at=now()))
    def add_user(self,username,password,role):
        if self.r.rows('users',username=username): return
        if len(password)<12: raise ValueError('Passwords require at least 12 characters')
        with self.r.transaction():
            self.r.insert('users',dict(id=uid(),username=username,password_hash=password_hash(password),role=role))
    def login(self,username,password):
        rows=self.r.rows('users',username=username)
        stored=rows[0]['password_hash'] if rows else password_hash('not-a-user-password')
        if not hmac.compare_digest(password_hash(password,stored.split(':')[0]),stored) or not rows:
            raise PermissionError('Invalid username or password')
        token=secrets.token_urlsafe(32)
        expiry=(datetime.now(timezone.utc)+timedelta(hours=8)).replace(tzinfo=None).isoformat()
        with self.r.transaction():
            self.r.insert('sessions',dict(id=hashlib.sha256(token.encode()).hexdigest(),user_id=rows[0]['id'],expires_at=expiry))
            self.audit(rows[0],'login',rows[0]['id'])
        return dict(token=token,user={k:rows[0][k] for k in ['id','username','role']})
    def user(self,token):
        sessions=self.r.rows('sessions',id=hashlib.sha256(token.encode()).hexdigest())
        if not sessions or str(sessions[0]['expires_at']).replace(' ','T') < now(): raise PermissionError('Session expired; sign in again')
        user=self.r.one('users',id=sessions[0]['user_id'])
        return {k:user[k] for k in ['id','username','role']}
    def logout(self,token):
        with self.r.transaction(): self.r.delete('sessions',hashlib.sha256(token.encode()).hexdigest())
    def validate_master(self,table,data,record_id=None):
        if table=='players':
            email=data.get('email','')
            if not isinstance(email,str) or len(email)>254: raise ValueError('Invalid email')
            provenance=data.get('provenance','synthetic')
            if provenance not in ['synthetic','consented']: raise ValueError('Invalid provenance')
            return dict(name=name_value(data.get('name')),email=email,provenance=provenance,archived=bool(data.get('archived',False)))
        if table=='tournaments':
            date.fromisoformat(data['start_date'])
            return dict(name=name_value(data.get('name'),160),start_date=data['start_date'],archived=bool(data.get('archived',False)))
        if table=='divisions':
            t=self.r.one('tournaments',id=data['tournament_id'])
            if t['archived']: raise ValueError('Tournament is archived')
            name=name_value(data.get('name'),80)
            if any(r['id']!=record_id and r['name'].casefold()==name.casefold() for r in self.r.rows('divisions',tournament_id=t['id'])):
                raise Conflict('Division name already used in this tournament')
            return dict(tournament_id=t['id'],name=name,cap=decimal_value(data['cap']),tolerance=decimal_value(data['tolerance']),rule_version=RULE)
        if table=='registrations':
            p=self.r.one('players',id=data['player_id']); d=self.r.one('divisions',id=data['division_id'])
            if p['archived'] or self.r.one('tournaments',id=d['tournament_id'])['archived']: raise ValueError('Archived player or tournament')
            if any(r['id']!=record_id for r in self.r.rows('registrations',player_id=p['id'],division_id=d['id'])):
                raise Conflict('Player already registered for this division')
            return dict(player_id=p['id'],division_id=d['id'],declared_rating=decimal_value(data['declared_rating']))
        if table=='matches':
            d=self.r.one('divisions',id=data['division_id'])
            if self.r.one('tournaments',id=d['tournament_id'])['archived']: raise ValueError('Tournament is archived')
            p1,p2=data['player1_id'],data['player2_id']
            if p1==p2: raise ValueError('Select two different players')
            for p in [p1,p2]:
                if self.r.one('players',id=p)['archived'] or not self.r.rows('registrations',player_id=p,division_id=d['id']):
                    raise ValueError('Both players must be active and registered in the division')
            return dict(division_id=d['id'],player1_id=p1,player2_id=p2)
        if table=='legs':
            m=self.r.one('matches',id=data['match_id']); number=data['number']
            if type(number) is not int or number<1: raise ValueError('Leg number must be a positive integer')
            if self.r.rows('legs',match_id=m['id'],number=number): raise Conflict('Leg number already exists')
            return dict(match_id=m['id'],number=number,accepted_revision=None,accepted_number=0)
        raise ValueError('Unknown resource')
    def create(self,table,data,user):
        permitted(user,'organiser')
        with self.r.transaction():
            values=self.validate_master(table,data); values['id']=uid()
            self.r.insert(table,values); self.audit(user,table+'_created',values['id'])
        return values
    def update(self,table,record_id,data,user):
        permitted(user,'organiser')
        if table not in ['players','tournaments','divisions','registrations']: raise ValueError('Fixture identities are immutable; create a new fixture')
        with self.r.transaction():
            old=self.r.one(table,id=record_id)
            if table=='divisions' and data.get('tournament_id',old['tournament_id'])!=old['tournament_id']: raise ValueError('Division cannot move tournaments')
            if table=='registrations' and any(data.get(k,old[k])!=old[k] for k in ['player_id','division_id']): raise ValueError('Registration participants are immutable')
            values=self.validate_master(table,dict(old,**data),record_id)
            self.r.update(table,record_id,values); self.audit(user,table+'_updated',record_id)
        return self.r.one(table,id=record_id)
    def remove(self,table,record_id,user):
        permitted(user,'organiser')
        if table not in ['players','tournaments','divisions','registrations','matches','legs']: raise ValueError('Unknown resource')
        with self.r.transaction():
            old=self.r.one(table,id=record_id)
            refs={'players':self.r.rows('registrations',player_id=record_id),
              'tournaments':self.r.rows('divisions',tournament_id=record_id),
              'divisions':self.r.rows('registrations',division_id=record_id)+self.r.rows('matches',division_id=record_id),
              'registrations':self.r.rows('matches',division_id=old.get('division_id',''),player1_id=old.get('player_id',''))+self.r.rows('matches',division_id=old.get('division_id',''),player2_id=old.get('player_id','')),
              'matches':self.r.rows('legs',match_id=record_id),
              'legs':[d for d in self.d.all('drafts')+self.d.all('revisions') if d['leg_id']==record_id]}
            if refs[table]:
                if table in ['players','tournaments']:
                    self.r.update(table,record_id,{'archived':True}); action='archived'
                else: raise Conflict('Referenced records are retained; remove unused child records first')
            else: self.r.delete(table,record_id); action='deleted'
            self.audit(user,table+'_'+action,record_id)
        return {'action':action}
    def context(self,leg_id):
        leg=self.r.one('legs',id=leg_id); match=self.r.one('matches',id=leg['match_id']); division=self.r.one('divisions',id=match['division_id'])
        return leg,match,division
    def create_draft(self,leg_id,user):
        permitted(user,'organiser','scorer')
        leg,match,_=self.context(leg_id)
        source=self.evidence(leg['accepted_revision']) if leg['accepted_revision'] else None
        doc=dict(_id=uid(),leg_id=leg_id,revision=leg['accepted_number']+1,base_revision=leg['accepted_number'],
          players=[match['player1_id'],match['player2_id']],status='completed',visits=source['visits'] if source else [],
          version=0,state='draft',created_by=user['id'])
        self.d.insert('drafts',doc)
        with self.r.transaction(): self.audit(user,'draft_created',doc['_id'])
        return doc
    def draft_access(self,key,user):
        permitted(user,'organiser','scorer'); d=self.d.get('drafts',key)
        if not d: raise ValueError('Draft not found')
        if user['role']=='scorer' and d['created_by']!=user['id']: raise PermissionError('Scorers can change only their own drafts')
        return d
    def save_draft(self,key,data,user):
        self.draft_access(key,user)
        visits=data.get('visits'); status=data.get('status')
        if not isinstance(visits,list) or len(visits)>1000 or status not in ['completed','abandoned']: raise ValueError('Invalid draft')
        # Drafts may be incomplete but board values and visit shape must be valid.
        from .scoring import dart_points
        for v in visits:
            if not isinstance(v,dict) or set(v)!={'player_id','darts'} or not isinstance(v['darts'],list) or not 1<=len(v['darts'])<=3:
                raise ValueError('Invalid visit shape')
            for dart in v['darts']: dart_points(dart)
        doc=self.d.change_draft(key,data['version'],{'visits':visits,'status':status})
        with self.r.transaction(): self.audit(user,'draft_saved',key,{'version':doc['version']})
        return doc
    def delete_draft(self,key,version,user):
        self.draft_access(key,user); self.d.delete_draft(key,version)
        with self.r.transaction(): self.audit(user,'draft_deleted',key)
        return {'deleted':True}
    def evidence(self,revision_id):
        doc=self.d.get('revisions',revision_id)
        records=self.r.rows('revisions',id=revision_id)
        if not doc or not records or digest(doc)!=doc['digest'] or digest(doc)!=records[0]['digest']:
            raise Conflict('Accepted evidence is missing or corrupt; reconcile before proceeding')
        # Recompute derived values to detect alteration of cached replay, too.
        if score(doc['players'],doc['visits'],doc['status'])!=doc['derived']: raise Conflict('Derived evidence mismatch')
        return doc
    def accept(self,key,version,user,fail_after_mongo=False):
        permitted(user,'organiser'); draft=self.draft_access(key,user)
        if draft['state']=='draft' and draft['version']!=version: raise Conflict('Draft version changed')
        if draft['state']=='frozen' and draft['version']!=version+1: raise Conflict('Frozen draft version mismatch')
        leg,match,division=self.context(draft['leg_id'])
        if draft['players']!=[match['player1_id'],match['player2_id']]: raise ValueError('Draft participants differ from fixture')
        derived=score(draft['players'],draft['visits'],draft['status'])
        if draft['state']=='draft': draft=self.d.change_draft(key,version,{'state':'frozen'})
        document={k:draft[k] for k in ['_id','leg_id','revision','base_revision','players','status','visits']}
        document.update(digest=digest(draft),derived=derived,created_by=user['id'],created_at=now())
        existing=self.d.get('revisions',key)
        if existing:
            if existing['digest']!=document['digest'] or existing['derived']!=derived: raise Conflict('Frozen revision differs')
        else: self.d.insert('revisions',document)
        if fail_after_mongo: raise RuntimeError('Injected failure after MongoDB insert')
        with self.r.transaction(leg_id=leg['id']):
            leg,match,division=self.context(draft['leg_id'])
            if self.r.rows('revisions',id=key): return dict(revision_id=key,idempotent=True)
            if leg['accepted_number']!=draft['base_revision']: raise Conflict('Stale correction; create a draft from the latest revision')
            self.r.insert('revisions',dict(id=key,leg_id=leg['id'],number=draft['revision'],digest=document['digest'],accepted_by=user['id'],created_at=now()))
            for review in self.r.rows('reviews',revision_id=leg['accepted_revision']): self.r.update('reviews',review['id'],{'status':'superseded'})
            for result in derived['results']:
                p=result['player_id']; eligible=result['eligible']
                flag=eligible and breached(result['points'],result['darts'],division['cap'],division['tolerance'])
                self.r.insert('results',dict(id=uid(),leg_id=leg['id'],revision_id=key,player_id=p,points=result['points'],darts=result['darts'],busts=result['busts'],eligible=eligible,winner=p==derived['winner_id']))
                self.r.insert('snapshots',dict(id=uid(),revision_id=key,player_id=p,cap=division['cap'],tolerance=division['tolerance'],rule_version=RULE,rating=result['rating'],breached=flag))
                if flag: self.r.insert('reviews',dict(id=uid(),revision_id=key,player_id=p,status='pending',note='',reviewed_by=None,reviewed_at=None))
            self.r.update('legs',leg['id'],dict(accepted_revision=key,accepted_number=draft['revision']))
            self.audit(user,'revision_accepted',key,{'digest':document['digest'],'base_revision':draft['base_revision']})
        return dict(revision_id=key,idempotent=False,derived=derived)
    def decide(self,key,status,note,user):
        permitted(user,'organiser')
        if status not in ['confirmed','dismissed'] or not isinstance(note,str) or not note.strip() or len(note)>1000: raise ValueError('Decision and a note of 1 to 1000 characters are required')
        initial=self.r.one('reviews',id=key)
        revision=self.r.one('revisions',id=initial['revision_id'])
        with self.r.transaction(leg_id=revision['leg_id']):
            review=self.r.one('reviews',id=key)
            if review['status']!='pending': raise Conflict('Only pending reviews can be decided')
            if not self.r.rows('legs',accepted_revision=review['revision_id']): raise Conflict('This review was superseded')
            self.evidence(review['revision_id'])
            self.r.update('reviews',key,dict(status=status,note=note.strip(),reviewed_by=user['id'],reviewed_at=now()))
            self.audit(user,'review_'+status,key,{'note':note})
        return self.r.one('reviews',id=key)
    def current_results(self):
        ids=[l['accepted_revision'] for l in self.r.rows('legs') if l['accepted_revision']]
        records={r['id']:r for r in self.r.rows('revisions')}
        documents={d['_id']:d for d in self.d.all('revisions') if d['_id'] in ids}
        for key in ids:
            doc=documents.get(key); record=records.get(key)
            if not doc or not record or digest(doc)!=record['digest'] or digest(doc)!=doc['digest']:
                raise Conflict('Accepted evidence is missing or corrupt; run reconciliation')
            if score(doc['players'],doc['visits'],doc['status'])!=doc['derived']:
                raise Conflict('Derived evidence mismatch; run reconciliation')
        return [r for r in self.r.rows('results') if r['revision_id'] in ids and r['eligible']]
    def rankings(self):
        # The live path demonstrates the accepted-results view and SQL window function.
        current=self.current_results() # fail closed on missing/corrupt evidence
        if self.r.mode=='live':
            return self.r.execute('''SELECT a.*,p.name,d.name division_name,
              DENSE_RANK() OVER(PARTITION BY division_id ORDER BY rating DESC) division_rank
              FROM accepted_results a JOIN players p ON p.id=a.player_id JOIN divisions d ON d.id=a.division_id
              WHERE a.eligible=1 ORDER BY division_id,division_rank,p.name''',read=True)
        out=[]; by={}
        for r in current:
            leg,match,d=self.context(r['leg_id']); rating=Decimal(3*r['points'])/Decimal(r['darts'])
            out.append(dict(r,name=self.r.one('players',id=r['player_id'])['name'],division_id=d['id'],division_name=d['name'],rating=str(rating)))
            by.setdefault(d['id'],set()).add(rating)
        for r in out: r['division_rank']=sorted(by[r['division_id']],reverse=True).index(Decimal(r['rating']))+1
        return sorted(out,key=lambda r:(r['division_id'],r['division_rank'],r['name']))
    def compare(self):
        current=self.current_results(); ids=[l['accepted_revision'] for l in self.r.rows('legs') if l['accepted_revision']]
        if self.r.mode=='live':
            sql=self.r.execute('''SELECT player_id,SUM(points) points,SUM(darts) darts,SUM(busts) busts,COUNT(*) legs
              FROM accepted_results WHERE eligible=1 GROUP BY player_id ORDER BY player_id''',read=True)
            sql=[{k:int(v) if k!='player_id' else v for k,v in r.items()} for r in sql]
        else:
            totals={}
            for r in current:
                t=totals.setdefault(r['player_id'],dict(player_id=r['player_id'],points=0,darts=0,busts=0,legs=0))
                for k in ['points','darts','busts']: t[k]+=r[k]
                t['legs']+=1
            sql=[r for _,r in sorted(totals.items())]
        mongo=self.d.aggregate(ids)
        return dict(mode=self.r.mode,equal=sql==mongo,relational=sql,documents=mongo,
          note='SQL reads accepted per-leg summaries; MongoDB expands validated visits. This compares outputs, not equal-cost query performance.')
    def reconcile(self):
        rows=self.r.rows('revisions'); known={r['id'] for r in rows}; missing=[]; corrupt=[]
        for r in rows:
            doc=self.d.get('revisions',r['id'])
            if not doc: missing.append(r['id']); continue
            try:
                if digest(doc)!=r['digest'] or digest(doc)!=doc['digest'] or score(doc['players'],doc['visits'],doc['status'])!=doc['derived']: corrupt.append(r['id'])
            except (ValueError,KeyError,TypeError): corrupt.append(r['id'])
        orphans=[d['_id'] for d in self.d.all('revisions') if d['_id'] not in known]
        return dict(ok=not(missing or corrupt or orphans),missing_evidence=missing,digest_mismatches=corrupt,orphan_revisions=orphans)
    def state(self,user):
        result={t:self.r.rows(t) for t in ['players','tournaments','divisions','registrations','matches','legs','reviews','snapshots']}
        result['drafts']=[d for d in self.d.all('drafts') if user['role']!='scorer' or d['created_by']==user['id']]
        result['audits']=sorted(self.r.rows('audits'),key=lambda a:str(a['created_at']),reverse=True)[:100] if user['role']=='organiser' else []
        result['user']=user; result['mode']=self.r.mode
        result['rankings']=self.rankings()
        return result
