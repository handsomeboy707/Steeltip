"""Straight-in, double-out 501. Domain validation shared by both runtime modes."""
from decimal import Decimal
from fractions import Fraction
import hashlib
import json

RULE = 'ST01-1.0'

def dart_points(d):
    if not isinstance(d, dict) or set(d) != {'segment', 'multiplier'}:
        raise ValueError('A dart needs segment and multiplier only')
    s, m = d['segment'], d['multiplier']
    if type(s) is not int or type(m) is not int:
        raise ValueError('Dart values must be integers')
    if s not in [0, *range(1, 21), 25] or m not in [1, 2, 3]:
        raise ValueError('Invalid board segment or multiplier')
    if (s == 0 and m != 1) or (s == 25 and m == 3):
        raise ValueError('Miss multiplier is 1; triple bull does not exist')
    return s * m

def score(players, visits, status='completed'):
    if len(players) != 2 or len(set(players)) != 2:
        raise ValueError('Two different participants required')
    if status not in ['completed', 'abandoned']:
        raise ValueError('Status must be completed or abandoned')
    if not isinstance(visits, list) or len(visits) > 1000:
        raise ValueError('At most 1000 visits allowed')
    totals = {p: dict(player_id=p, points=0, darts=0, busts=0, remaining=501) for p in players}
    replay, winner = [], None
    for n, visit in enumerate(visits):
        if winner: raise ValueError('No throws after checkout')
        if not isinstance(visit,dict) or set(visit) != {'player_id','darts'}:
            raise ValueError('Each visit needs player_id and darts only')
        p, darts = visit['player_id'], visit['darts']
        if p != players[n % 2]: raise ValueError('Players must alternate, starting with player one')
        if not isinstance(darts,list) or not 1 <= len(darts) <= 3: raise ValueError('One to three actual darts per visit')
        start = remaining = totals[p]['remaining']
        bust = False
        for i, dart in enumerate(darts):
            remaining -= dart_points(dart)
            bust = remaining < 0 or remaining == 1 or (remaining == 0 and dart['multiplier'] != 2)
            if bust or remaining == 0:
                if i != len(darts)-1: raise ValueError('Extra darts recorded after bust or checkout')
                break
        if not bust and remaining != 0 and len(darts) != 3:
            raise ValueError('An unfinished visit requires three darts')
        credited = 0 if bust else start - remaining
        totals[p]['remaining'] = start if bust else remaining
        totals[p]['points'] += credited
        totals[p]['darts'] += len(darts)
        totals[p]['busts'] += int(bust)
        replay.append(dict(number=n+1,player_id=p,start=start,remaining=totals[p]['remaining'],
                           points=credited,darts=len(darts),bust=bust))
        if not bust and remaining == 0: winner = p
    if status == 'completed' and not winner: raise ValueError('Completed legs require a legal double checkout')
    if status == 'abandoned' and winner: raise ValueError('A checked-out leg cannot be abandoned')
    for r in totals.values():
        r['eligible'] = status == 'completed' and r['darts'] > 0
        r['rating'] = str(Decimal(3*r['points'])/Decimal(r['darts'])) if r['eligible'] else None
    return dict(status=status,winner_id=winner,results=list(totals.values()),replay=replay)

def breached(points, darts, cap, tolerance):
    return darts > 0 and Fraction(3*points,darts) > Fraction(Decimal(str(cap))+Decimal(str(tolerance)))

def digest(doc):
    keys = ['leg_id','revision','base_revision','players','status','visits']
    return hashlib.sha256(json.dumps({k:doc[k] for k in keys},sort_keys=True,separators=(',',':')).encode()).hexdigest()
