import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .storage import DemoRelational,DemoDocuments,MariaRelational,MongoDocuments,Conflict
from .service import Application
from .api import dispatch
from .dataset import seed

ROOT=Path(__file__).resolve().parents[1]
def json_default(value):
    if isinstance(value,(datetime,date)): return value.isoformat()
    if isinstance(value,Decimal): return str(value)
    raise TypeError(type(value).__name__)
def create_application(live=False,seed_data=True):
    r=MariaRelational() if live else DemoRelational(ROOT/'runtime'/'relational-demo.json')
    d=MongoDocuments() if live else DemoDocuments(ROOT/'runtime'/'documents-demo.json')
    app=Application(r,d)
    for username,role,key in [('organiser','organiser','ORGANISER_PASSWORD'),('scorer','scorer','SCORER_PASSWORD'),('viewer','viewer','VIEWER_PASSWORD')]:
        password=os.environ.get(key) if live else 'demo-'+username+'-26'
        if not password: raise RuntimeError(key+' must be configured')
        app.add_user(username,password,role)
    if seed_data:
        # Avoid serialising the whole JSON demo after every seed insert; live DBs keep transactions.
        rpath=getattr(r,'path',None); dpath=getattr(d,'path',None)
        if not live: r.path=None; d.path=None
        try: seed(app)
        finally:
            if not live: r.path=rpath; d.path=dpath; r.flush(); d.flush()
    return app

def error_status(exc):
    if isinstance(exc,PermissionError): return 403
    if isinstance(exc,Conflict): return 409
    if isinstance(exc,LookupError) and not isinstance(exc,KeyError): return 404
    if isinstance(exc,(ValueError,KeyError,TypeError)): return 422
    try:
        from pymysql import IntegrityError
        if isinstance(exc,IntegrityError): return 409
    except ImportError: pass
    return 503

def fastapi_application(application):
    from fastapi import FastAPI,Request
    from fastapi.responses import JSONResponse,FileResponse
    from fastapi.staticfiles import StaticFiles
    api=FastAPI(title='Steel Tip 01 Manager',version='1.0.0')
    @api.api_route('/api/{rest:path}',methods=['GET','POST','PUT','DELETE'])
    async def route(request:Request,rest:str):
        try:
            raw=await request.body()
            if len(raw)>2_000_000: return JSONResponse({'error':'Request too large'},status_code=413)
            body=json.loads(raw) if raw else {}
            if not isinstance(body,dict): raise ValueError('JSON object required')
            token=request.headers.get('authorization','').removeprefix('Bearer ')
            # Database work is synchronous: run in a worker, preserving thread-local SQL transactions.
            from starlette.concurrency import run_in_threadpool
            result=await run_in_threadpool(dispatch,application,request.method,'/api/'+rest,body,token)
            return JSONResponse(json.loads(json.dumps(result,default=json_default)),headers={'Cache-Control':'no-store'})
        except Exception as e:
            status=error_status(e)
            return JSONResponse({'error':str(e) if status<500 else 'Database operation unavailable; check server logs'},status_code=status)
    api.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='web')
    return api

def serve_demo(application,host,port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,fmt,*args): pass
        def do_GET(self): self.handle_request()
        def do_POST(self): self.handle_request()
        def do_PUT(self): self.handle_request()
        def do_DELETE(self): self.handle_request()
        def handle_request(self):
            path=urlparse(self.path).path
            if path.startswith('/api/'):
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if size<0 or size>2_000_000: raise ValueError('Request too large')
                    body=json.loads(self.rfile.read(size)) if size else {}
                    if not isinstance(body,dict): raise ValueError('JSON object required')
                    token=self.headers.get('Authorization','').removeprefix('Bearer ')
                    result=dispatch(application,self.command,path,body,token); status=200
                except Exception as exc: status=error_status(exc); result={'error':str(exc) if status<500 else 'Operation unavailable'}
                content=json.dumps(result,default=json_default).encode(); mime='application/json'
            else:
                target=(ROOT/'web'/('index.html' if path=='/' else path.lstrip('/'))).resolve()
                if not target.is_relative_to((ROOT/'web').resolve()) or not target.is_file():
                    self.send_error(404); return
                content=target.read_bytes(); status=200
                mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'}.get(target.suffix,'application/octet-stream')
            self.send_response(status); self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Content-Length',str(len(content))); self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(content)
    print(f'SteelTip offline demo: http://{host}:{port}',flush=True)
    print('Demo logins: organiser / demo-organiser-26, scorer / demo-scorer-26, viewer / demo-viewer-26',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--live',action='store_true'); parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--no-seed',action='store_true'); args=parser.parse_args()
    if not args.live and not args.no_seed and not (ROOT/'runtime'/'documents-demo.json').exists():
        print('Preparing the 500-leg practice fixture. Open the app when the local URL appears.', flush=True)
    app=create_application(args.live,not args.no_seed)
    if args.live:
        import uvicorn
        uvicorn.run(fastapi_application(app),host='0.0.0.0',port=args.port)
    else: serve_demo(app,'127.0.0.1',args.port)
