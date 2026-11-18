"""Reproducible synthetic fixtures. No real players or consent claims."""
import json
import random
from pathlib import Path
from statistics import median, quantiles
from uuid import uuid5, NAMESPACE_URL
from .scoring import breached, dart_points, score, RULE

SEED=26012026
VALIDATION_SEED=26012027
# Per-player scoring skill varies within each division. The review limits apply
# to individual legs, which vary more than a player's multi-match average.
DIVISIONS = (
    ('Community', 66, (.035, .10), (.12, .23), 45),
    ('Premier', 88, (.13, .23), (.22, .36), 59),
)

def sid(text): return str(uuid5(NAMESPACE_URL,'steeltip-group26:'+text))

def simulated_dart(remaining, treble, double, rng):
    chance = rng.random()
    if remaining <= 50 and remaining % 2 == 0 and (remaining <= 40 or remaining == 50):
        target = remaining // 2
        if chance < double:
            return {'segment': target, 'multiplier': 2}
        if target != 25 and chance < double + .42:
            return {'segment': target, 'multiplier': 1}
        if chance < double + .52:
            return {'segment': rng.choice((1, 5, 12, 18, 20)), 'multiplier': 1}
        return {'segment': 0, 'multiplier': 1}
    if remaining <= 61:
        # Set up a double when there is no direct checkout.
        target = min(20, remaining - 2)
        if (remaining - target) % 2:
            target -= 1
        segment = target if chance < .72 else rng.choice((0, 1, 5, 12, 20))
        return {'segment': segment, 'multiplier': 1}
    if chance < treble:
        return {'segment': 20, 'multiplier': 3}
    if chance < treble + .08:
        return {'segment': rng.choice((18, 19)), 'multiplier': 2}
    if chance < .52:
        return {'segment': 20, 'multiplier': 1}
    return {'segment': rng.choice((0, 0, 1, 1, 5, 5, 12, 18)), 'multiplier': 1}

def generate_visits(players, rng, skills=((.10, .21), (.12, .23))):
    remaining={p:501 for p in players}; visits=[]; winner=None
    form = [max(.02, treble + rng.uniform(-.055, .055)) for treble, _ in skills]
    for visit_number in range(1000):
        slot = visit_number % 2
        p=players[slot]; start=current=remaining[p]; darts=[]; bust=False
        for _ in range(3):
            d = simulated_dart(current, form[slot], skills[slot][1], rng)
            darts.append(d); current-=dart_points(d)
            bust=current<0 or current==1 or (current==0 and d['multiplier']!=2)
            if bust or current==0: break
        remaining[p]=start if bust else current
        visits.append({'player_id':p,'darts':darts})
        if not bust and current==0: winner=p; break
    if not winner: raise RuntimeError('Synthetic generator failed to finish')
    return visits

def generate(seed_value=SEED):
    rng=random.Random(seed_value)
    data={k:[] for k in ['players','tournaments','divisions','registrations','matches','legs','evidence']}
    for i in range(100):
        data['players'].append(dict(id=sid('player'+str(i)),name=f'Synthetic Player {i+1:03}',email='',archived=False,provenance='synthetic'))
    for t in range(5):
        tournament=dict(id=sid('tournament'+str(t)),name=f'SteelTip Synthetic Open {t+1}',start_date=f'2026-11-{1+7*t:02}',archived=False)
        data['tournaments'].append(tournament)
        for d, (name, cap, treble_range, double_range, baseline) in enumerate(DIVISIONS):
            division=dict(id=sid(f'division{t}-{d}'),tournament_id=tournament['id'],name=name,cap=str(cap),tolerance='2',rule_version=RULE)
            data['divisions'].append(division)
            players=data['players'][20*t+d:20*(t+1):2]
            for p in players:
                data['registrations'].append(dict(id=sid('registration'+p['id']),player_id=p['id'],division_id=division['id'],declared_rating=str(baseline+rng.randrange(-5,6))))
            for pair in range(5):
                p1,p2=players[2*pair]['id'],players[2*pair+1]['id']
                skills=[(rng.uniform(*treble_range),rng.uniform(*double_range)) for _ in (p1,p2)]
                match=dict(id=sid(f'match{t}-{d}-{pair}'),division_id=division['id'],player1_id=p1,player2_id=p2)
                data['matches'].append(match)
                for n in range(1,11):
                    leg=dict(id=sid(f'leg{t}-{d}-{pair}-{n}'),match_id=match['id'],number=n,accepted_revision=None,accepted_number=0)
                    data['legs'].append(leg)
                    data['evidence'].append(dict(leg_id=leg['id'],players=[p1,p2],status='completed',visits=generate_visits([p1,p2],rng,skills)))
    data['metadata']=dict(provenance='synthetic',seed=seed_value,players=100,tournaments=5,divisions=10,matches=50,legs=500,
        policy='Straight in double out, simulated ordinary play without injected cheating',
        verification=summarise(data))
    return data

def summarise(data):
    divisions = {d['id']: d for d in data['divisions']}
    matches = {m['id']: divisions[m['division_id']] for m in data['matches']}
    legs = {l['id']: matches[l['match_id']] for l in data['legs']}
    bands = {}
    for e in data['evidence']:
        div = legs[e['leg_id']]
        derived = score(e['players'], e['visits'], e['status'])
        band = bands.setdefault(div['name'], dict(legs=0, flagged_legs=0, flagged_results=0,
                                                 darts=0, busts=0, ratings=[]))
        band['legs'] += 1
        results = derived['results']
        flags = sum(breached(r['points'], r['darts'], div['cap'], div['tolerance']) for r in results)
        band['flagged_results'] += flags
        band['flagged_legs'] += bool(flags)
        band['darts'] += sum(r['darts'] for r in results)
        band['busts'] += sum(r['busts'] for r in results)
        band['ratings'].extend(float(r['rating']) for r in results)
    for band in bands.values():
        ratings = band.pop('ratings')
        band['results'] = len(ratings)
        band['median_rating'] = round(median(ratings), 2)
        band['p95_rating'] = round(quantiles(ratings, n=100)[94], 2)
    return bands

def seed(application):
    if application.r.rows('audits',action='synthetic_seed_completed'): return False
    # An existing non-seed dataset is preserved. Use --no-seed for a blank installation.
    existing=application.r.rows('players')
    if existing and not any(p['id']==sid('player0') for p in existing): return False
    path=Path(__file__).resolve().parents[1]/'data'/'synthetic_dataset.json'
    data=json.loads(path.read_text()) if path.exists() else generate()
    user=application.r.one('users',username='organiser')
    with application.r.transaction():
        for table in ['players','tournaments','divisions','registrations','matches','legs']:
            for row in data[table]:
                if not application.r.rows(table,id=row['id']): application.r.insert(table,row)
        application.audit(user,'synthetic_dataset_loaded','dataset',data['metadata'])
    drafts_by_leg = {}
    for draft in application.d.all('drafts'):
        drafts_by_leg.setdefault(draft['leg_id'], draft)
    for evidence in data['evidence']:
        leg=application.r.one('legs',id=evidence['leg_id'])
        if leg['accepted_revision']: continue
        draft=drafts_by_leg.get(leg['id']) or application.create_draft(leg['id'],user)
        if draft['state']=='draft':
            draft=application.save_draft(draft['_id'],dict(visits=evidence['visits'],status=evidence['status'],version=draft['version']),user)
        application.accept(draft['_id'],draft['version']-1 if draft['state']=='frozen' else draft['version'],user)
    with application.r.transaction(): application.audit(user,'synthetic_seed_completed','dataset',data['metadata'])
    return True

if __name__=='__main__':
    path=Path(__file__).resolve().parents[1]/'data'/'synthetic_dataset.json'
    path.parent.mkdir(exist_ok=True); data=generate(); path.write_text(json.dumps(data,separators=(',',':')))
    print(json.dumps({'fixture':data['metadata'],'validation':generate(VALIDATION_SEED)['metadata']},indent=2))
