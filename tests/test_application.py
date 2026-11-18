import copy
import random
import unittest
from decimal import Decimal
from app.scoring import score,breached,dart_points
from app.storage import DemoRelational,DemoDocuments,Conflict
from app.service import Application
from app.dataset import generate,generate_visits
from app.api import dispatch

def visit(p,*darts): return {'player_id':p,'darts':[{'segment':s,'multiplier':m} for s,m in darts]}
def checkout_visits():
    return [visit('a',(20,3),(20,3),(20,3)),visit('b',(20,1),(20,1),(0,1)),
      visit('a',(20,3),(20,3),(20,3)),visit('b',(20,1),(20,1),(0,1)),
      visit('a',(20,3),(19,3),(12,2))]

class ScoringTests(unittest.TestCase):
    def test_nine_dart_checkout(self):
        r=score(['a','b'],checkout_visits()); self.assertEqual(r['winner_id'],'a')
        self.assertEqual(r['results'][0]['points'],501); self.assertEqual(r['results'][0]['darts'],9)
        self.assertEqual(Decimal(r['results'][0]['rating']),167)
    def test_misses_are_actual_darts(self): self.assertEqual(score(['a','b'],checkout_visits())['results'][1]['darts'],6)
    def test_bust_below_zero_restores_entire_visit(self):
        v=checkout_visits()[:-1]+[visit('a',(20,3),(20,3),(20,3))]
        r=score(['a','b'],v,'abandoned'); self.assertEqual(r['results'][0]['remaining'],141); self.assertEqual(r['results'][0]['points'],360)
        self.assertEqual(r['results'][0]['busts'],1); self.assertEqual(r['results'][0]['darts'],9)
    def test_remaining_one_is_bust_and_partial_actual_count(self):
        v=checkout_visits()[:-1]+[visit('a',(20,3),(20,3),(20,1))]
        r=score(['a','b'],v,'abandoned'); self.assertEqual(r['results'][0]['remaining'],141)
    def test_zero_without_double_is_bust(self):
        v=checkout_visits()[:-1]+[visit('a',(20,3),(19,3),(8,3))]
        self.assertEqual(score(['a','b'],v,'abandoned')['results'][0]['busts'],1)
    def test_partial_bust_counts_only_thrown_darts(self):
        v=[visit('a',(20,3),(20,3),(20,3)),visit('b',(0,1),(0,1),(0,1)),visit('a',(20,3),(20,3),(20,3)),
          visit('b',(0,1),(0,1),(0,1)),visit('a',(20,3),(20,3),(19,1)),visit('b',(0,1),(0,1),(0,1)),visit('a',(20,3))]
        r=score(['a','b'],v,'abandoned')['results'][0]; self.assertEqual((r['remaining'],r['darts'],r['busts']),(2,10,1))
    def test_extra_darts_after_bust_rejected(self):
        v=[visit('a',(20,3),(20,3),(20,3)),visit('b',(0,1),(0,1),(0,1)),visit('a',(20,3),(20,3),(20,3)),visit('b',(0,1),(0,1),(0,1)),
          visit('a',(20,3),(20,3),(19,1)),visit('b',(0,1),(0,1),(0,1)),visit('a',(20,3),(0,1))]
        with self.assertRaises(ValueError): score(['a','b'],v,'abandoned')
    def test_visit_order_rejected(self):
        v=checkout_visits(); v[1]['player_id']='a'
        with self.assertRaises(ValueError): score(['a','b'],v)
    def test_post_checkout_visit_rejected(self):
        with self.assertRaises(ValueError): score(['a','b'],checkout_visits()+[visit('b',(0,1),(0,1),(0,1))])
    def test_partial_unfinished_visit_rejected(self):
        with self.assertRaises(ValueError): score(['a','b'],[visit('a',(20,1))],'abandoned')
    def test_no_checkout_cannot_complete(self):
        with self.assertRaises(ValueError): score(['a','b'],[])
    def test_abandoned_and_zero_darts_excluded(self): self.assertFalse(any(r['eligible'] for r in score(['a','b'],[],'abandoned')['results']))
    def test_cap_equality_is_not_breach(self): self.assertFalse(breached(501,9,'165','2'))
    def test_strict_boundary_no_rounding(self): self.assertTrue(breached(501,9,'164.9999','2'))
    def test_zero_darts_not_breach(self): self.assertFalse(breached(501,0,1,0))
    def test_invalid_board_and_boolean_values(self):
        for d in [{'segment':25,'multiplier':3},{'segment':0,'multiplier':2},{'segment':True,'multiplier':1},{'segment':21,'multiplier':1}]:
            with self.assertRaises(ValueError): dart_points(d)

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app=Application(DemoRelational(),DemoDocuments()); self.app.add_user('organiser','test-organiser-26','organiser')
        self.user=self.app.r.one('users',username='organiser')
        self.app.add_user('scorer','test-scorer-pass26','scorer'); self.scorer=self.app.r.one('users',username='scorer')
        self.viewer={'id':'viewer','role':'viewer','username':'viewer'}
        self.p1=self.app.create('players',{'name':'Alpha'},self.user); self.p2=self.app.create('players',{'name':'Beta'},self.user)
        self.t=self.app.create('tournaments',{'name':'Test Open','start_date':'2026-11-03'},self.user)
        self.div=self.app.create('divisions',{'tournament_id':self.t['id'],'name':'Community','cap':'55','tolerance':'2'},self.user)
        for p in [self.p1,self.p2]: self.app.create('registrations',{'player_id':p['id'],'division_id':self.div['id'],'declared_rating':'40'},self.user)
        self.match=self.app.create('matches',{'division_id':self.div['id'],'player1_id':self.p1['id'],'player2_id':self.p2['id']},self.user)
        self.leg=self.app.create('legs',{'match_id':self.match['id'],'number':1},self.user)
    def ready(self,user=None):
        user=user or self.user; d=self.app.create_draft(self.leg['id'],user)
        visits=checkout_visits()
        for v in visits: v['player_id']={'a':self.p1['id'],'b':self.p2['id']}[v['player_id']]
        return self.app.save_draft(d['_id'],{'version':0,'status':'completed','visits':visits},user)
    def test_duplicate_registration(self):
        with self.assertRaises(Conflict): self.app.create('registrations',{'player_id':self.p1['id'],'division_id':self.div['id'],'declared_rating':'40'},self.user)
    def test_unregistered_participant_rejected(self):
        p=self.app.create('players',{'name':'Unregistered'},self.user)
        with self.assertRaises(ValueError): self.app.create('matches',{'division_id':self.div['id'],'player1_id':self.p1['id'],'player2_id':p['id']},self.user)
    def test_viewer_write_denied(self):
        with self.assertRaises(PermissionError): self.app.create('players',{'name':'No'},self.viewer)
    def test_scorer_cannot_verify(self):
        d=self.ready(self.scorer)
        with self.assertRaises(PermissionError): self.app.accept(d['_id'],d['version'],self.scorer)
    def test_scorer_cannot_change_other_draft(self):
        d=self.ready()
        with self.assertRaises(PermissionError): self.app.save_draft(d['_id'],{'version':1,'status':'completed','visits':d['visits']},self.scorer)
    def test_stale_draft_version(self):
        d=self.ready()
        with self.assertRaises(Conflict): self.app.save_draft(d['_id'],{'version':0,'status':'completed','visits':d['visits']},self.user)
    def test_accept_and_equivalent_aggregates(self):
        d=self.ready(); self.app.accept(d['_id'],d['version'],self.user)
        self.assertTrue(self.app.compare()['equal']); self.assertEqual(len(self.app.current_results()),2)
        self.assertEqual(len(self.app.r.rows('reviews')),1); self.assertTrue(self.app.reconcile()['ok'])
    def test_accepted_draft_immutable(self):
        d=self.ready(); self.app.accept(d['_id'],d['version'],self.user)
        with self.assertRaises(Conflict): self.app.save_draft(d['_id'],{'version':2,'status':'completed','visits':d['visits']},self.user)
    def test_idempotent_acceptance(self):
        d=self.ready(); self.app.accept(d['_id'],d['version'],self.user)
        self.assertTrue(self.app.accept(d['_id'],d['version'],self.user)['idempotent'])
        self.assertEqual(len(self.app.r.rows('results')),2)
    def test_correction_preserves_history_and_supersedes_review(self):
        d=self.ready(); self.app.accept(d['_id'],d['version'],self.user)
        correction=self.app.create_draft(self.leg['id'],self.user); self.app.accept(correction['_id'],0,self.user)
        self.assertEqual(len(self.app.d.all('revisions')),2); self.assertEqual(len(self.app.current_results()),2)
        self.assertEqual(self.app.r.rows('reviews',revision_id=d['_id'])[0]['status'],'superseded')
        self.assertTrue(self.app.compare()['equal'])
    def test_stale_correction_rejected(self):
        d1=self.ready(); d2=self.ready(); self.app.accept(d1['_id'],1,self.user)
        with self.assertRaises(Conflict): self.app.accept(d2['_id'],1,self.user)
    def test_interrupted_write_and_safe_retry(self):
        d=self.ready()
        with self.assertRaises(RuntimeError): self.app.accept(d['_id'],1,self.user,fail_after_mongo=True)
        self.assertEqual(len(self.app.r.rows('results')),0); self.assertEqual(self.app.reconcile()['orphan_revisions'],[d['_id']])
        self.app.accept(d['_id'],1,self.user); self.assertTrue(self.app.reconcile()['ok'])
    def test_missing_evidence_fail_closed(self):
        d=self.ready(); self.app.accept(d['_id'],1,self.user); del self.app.d.data['revisions'][d['_id']]
        with self.assertRaises(Conflict): self.app.current_results()
        self.assertEqual(self.app.reconcile()['missing_evidence'],[d['_id']])
    def test_changed_derived_results_detected(self):
        d=self.ready(); self.app.accept(d['_id'],1,self.user); self.app.d.data['revisions'][d['_id']]['derived']['results'][0]['points']=0
        with self.assertRaises(Conflict): self.app.current_results()
    def test_referenced_player_archived(self):
        self.assertEqual(self.app.remove('players',self.p1['id'],self.user)['action'],'archived')
    def test_delete_unused_player(self):
        p=self.app.create('players',{'name':'Unused'},self.user); self.assertEqual(self.app.remove('players',p['id'],self.user)['action'],'deleted')
    def test_review_requires_note_and_is_audited(self):
        d=self.ready();self.app.accept(d['_id'],1,self.user); review=self.app.r.rows('reviews')[0]
        with self.assertRaises(ValueError): self.app.decide(review['id'],'dismissed','',self.user)
        self.app.decide(review['id'],'dismissed','Practice fixture checked',self.user)
        self.assertEqual(self.app.r.one('reviews',id=review['id'])['status'],'dismissed')
    def test_login_dispatch_and_logout(self):
        response=dispatch(self.app,'POST','/api/login',{'username':'organiser','password':'test-organiser-26'},'')
        self.assertEqual(self.app.user(response['token'])['role'],'organiser'); self.app.logout(response['token'])
        with self.assertRaises(PermissionError): self.app.user(response['token'])
    def test_invalid_numeric_threshold(self):
        for x in ['NaN','-1','0.00001']:
            with self.assertRaises(ValueError): self.app.update('divisions',self.div['id'],{'cap':x},self.user)

class DatasetTests(unittest.TestCase):
    def test_all_500_legs_legal_and_reproducible(self):
        a=generate(); self.assertEqual(a,generate()); self.assertEqual(len(a['players']),100); self.assertEqual(len(a['tournaments']),5); self.assertEqual(len(a['legs']),500)
        busts=misses=0
        for leg in a['evidence']:
            result=score(leg['players'],leg['visits']); self.assertTrue(result['winner_id'])
            self.assertEqual(sum(r['points']==501 for r in result['results']),1)
            busts+=sum(r['busts'] for r in result['results']); misses+=sum(d['segment']==0 for v in leg['visits'] for d in v['darts'])
        self.assertGreater(busts,0); self.assertGreater(misses,0)

if __name__=='__main__': unittest.main()
