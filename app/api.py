"""Framework-neutral API dispatcher. Called by FastAPI and the offline HTTP server."""
from .scoring import score
from .service import permitted

def dispatch(app,method,path,body,token):
    if method=='GET' and path=='/api/health':
        return {'mode':app.r.mode,'ready':True,'databases':'MariaDB + MongoDB' if app.r.mode=='live' else 'Offline JSON demo; no DBMS'}
    if method=='POST' and path=='/api/login': return app.login(body.get('username',''),body.get('password',''))
    user=app.user(token)
    if method=='POST' and path=='/api/logout': app.logout(token); return {'signed_out':True}
    if method=='GET' and path=='/api/state': return app.state(user)
    if method=='GET' and path=='/api/diagnostics':
        permitted(user,'organiser')
        from .diagnostics import inspect_databases
        return inspect_databases(app)
    if method=='GET' and path=='/api/compare': return app.compare()
    if method=='GET' and path=='/api/reconcile': permitted(user,'organiser'); return app.reconcile()
    if method=='GET' and path.startswith('/api/example/'):
        permitted(user,'organiser','scorer')
        from .dataset import generate_visits
        import random
        leg,match,_=app.context(path.rsplit('/',1)[1])
        return {'provenance':'synthetic','visits':generate_visits([match['player1_id'],match['player2_id']],random.Random(26))}
    if method=='POST' and path=='/api/validate':
        permitted(user,'organiser','scorer'); return score(body['players'],body['visits'],body.get('status','completed'))
    parts=path.strip('/').split('/')
    if len(parts)==3 and parts[:2]==['api','records'] and method=='POST': return app.create(parts[2],body,user)
    if len(parts)==4 and parts[:2]==['api','records']:
        if method=='PUT': return app.update(parts[2],parts[3],body,user)
        if method=='DELETE': return app.remove(parts[2],parts[3],user)
    if len(parts)==3 and parts[:2]==['api','drafts']:
        if method=='POST': return app.create_draft(parts[2],user)
        if method=='PUT': return app.save_draft(parts[2],body,user)
        if method=='DELETE': return app.delete_draft(parts[2],body['version'],user)
    if len(parts)==4 and parts[:2]==['api','drafts'] and parts[3]=='accept' and method=='POST':
        return app.accept(parts[2],body['version'],user)
    if len(parts)==3 and parts[:2]==['api','evidence'] and method=='GET': return app.evidence(parts[2])
    if len(parts)==3 and parts[:2]==['api','reviews'] and method=='PUT': return app.decide(parts[2],body['status'],body['note'],user)
    raise LookupError('Endpoint not found')
