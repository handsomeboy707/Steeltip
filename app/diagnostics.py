"""Authenticated, read-only database observations, never canned connection badges."""
# The app account can read the view but has no SHOW VIEW privilege. Explain
# the equivalent base-table query with the same joins and filters.
SUMMARY_PLAN_SQL = '''SELECT r.player_id,SUM(r.points) points,SUM(r.darts) darts,
SUM(r.busts) busts,COUNT(*) legs
FROM results r JOIN legs l ON l.id=r.leg_id AND l.accepted_revision=r.revision_id
JOIN matches m ON m.id=l.match_id JOIN revisions v ON v.id=r.revision_id
WHERE r.eligible=1{scope} GROUP BY r.player_id ORDER BY r.player_id'''

def inspect_databases(app):
    if app.r.mode != 'live':
        return {'mode': 'offline', 'verified_live': False,
                'message': 'JSON demonstration adapters. No MariaDB or MongoDB connection is verified.'}
    from .storage import pipeline
    app.r.execute('SELECT 1 AS connected', read=True)
    app.d.db.command('ping')
    ids = [r['accepted_revision'] for r in app.r.rows('legs') if r['accepted_revision']]
    comparison = app.compare()
    return {'mode': 'live', 'verified_live': True,
            'mariadb_version': app.r.execute('SELECT VERSION() AS version', read=True)[0]['version'],
            'mongodb_version': app.d.db.client.server_info()['version'],
            'accepted_legs': len(ids), 'aggregate_players': len(comparison['relational']),
            'equal_outputs': comparison['equal'],
            'sql_explain': app.r.execute('EXPLAIN ' + SUMMARY_PLAN_SQL.format(scope=''), read=True),
            'mongo_pipeline': pipeline(ids),
            'mongo_indexes': list(app.d.db.revisions.list_indexes()),
            'note': 'Observations at request time. Equality checks all player IDs and point/dart/bust/leg totals. No latency is inferred.'}
