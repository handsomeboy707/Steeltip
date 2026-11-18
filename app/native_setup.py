"""Local Windows database setup. Administrator passwords are prompted, never saved."""
import argparse
import getpass
import json
import os
import secrets
import socket
from pathlib import Path
from urllib.parse import quote
from .storage import FIELDS

ROOT=Path(__file__).resolve().parents[1]
SETTINGS=ROOT/'runtime'/'native-settings.json'
MUTABLE=('players','tournaments','divisions','registrations','matches','legs','reviews','sessions')
INSERT_ONLY=('users','revisions','results','snapshots','audits')

def fresh_settings(sql_port=3306,mongo_port=27017):
    suffix=secrets.token_hex(4);sql_user='steeltip_app_'+suffix;mongo_user='steeltip_app_'+suffix
    sql_password=secrets.token_hex(24);mongo_password=secrets.token_hex(24)
    return {'format':1,'setup_complete':False,'sql_port':sql_port,'mongo_port':mongo_port,
      'sql_user':sql_user,'mongo_user':mongo_user,'mongo_password':mongo_password,
      'mongo_role':'steeltipApplication_'+suffix,'environment':{
        'SQL_HOST':'127.0.0.1','SQL_PORT':str(sql_port),'SQL_USER':sql_user,'SQL_PASSWORD':sql_password,
        'MONGO_URI':f'mongodb://{quote(mongo_user,safe="")}:{quote(mongo_password,safe="")}@127.0.0.1:{mongo_port}/steeltip?authSource=steeltip',
        'ORGANISER_PASSWORD':secrets.token_urlsafe(24),'SCORER_PASSWORD':secrets.token_urlsafe(24),
        'VIEWER_PASSWORD':secrets.token_urlsafe(24)}}

def save_settings(settings,path=SETTINGS):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(settings,indent=2)+'\n',encoding='utf-8');temp.replace(path)

def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=2): return True
    except OSError:return False

def ensure_sql_schema(cursor):
    cursor.execute('CREATE DATABASE IF NOT EXISTS steeltip CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    cursor.execute('USE steeltip')
    cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='steeltip' AND TABLE_TYPE='BASE TABLE'")
    existing={row[0] for row in cursor.fetchall()}
    expected=set(FIELDS)
    if existing and existing!=expected:
        raise RuntimeError('The existing steeltip SQL database has a different or incomplete schema. Nothing has been deleted. Resolve it before continuing.')
    statements=[s.strip() for s in (ROOT/'sql'/'001_schema.sql').read_text(encoding='utf-8').split(';') if s.strip()]
    if not existing:
        for statement in statements:cursor.execute(statement)
    else:
        for table,fields in FIELDS.items():
            cursor.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='steeltip' AND TABLE_NAME=%s",(table,))
            if {r[0] for r in cursor.fetchall()}!=set(fields):
                raise RuntimeError('The existing SQL table '+table+' does not match this application. No existing data were overwritten.')
        cursor.execute("SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA='steeltip' AND TABLE_NAME='accepted_results'")
        if not cursor.fetchone():
            for statement in statements:
                if statement.startswith('CREATE VIEW accepted_results'):cursor.execute(statement)

def setup_sql(settings):
    import pymysql
    print('\nMariaDB administrator login (the same server account you use in HeidiSQL).')
    username=input('MariaDB username [root]: ').strip() or 'root'
    password=getpass.getpass('MariaDB password (hidden; Enter if you deliberately left it blank): ')
    connection=pymysql.connect(host='127.0.0.1',port=settings['sql_port'],user=username,password=password,charset='utf8mb4',autocommit=True,connect_timeout=5)
    try:
        with connection.cursor() as cursor:
            ensure_sql_schema(cursor)
            # Account names are values, not SQL identifiers; parameterise them.
            for host in ['localhost','127.0.0.1']:
                user=settings['sql_user'];secret=settings['environment']['SQL_PASSWORD']
                cursor.execute('CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s',(user,host,secret))
                cursor.execute('GRANT SELECT ON steeltip.* TO %s@%s',(user,host))
                for table in MUTABLE:
                    cursor.execute('GRANT INSERT,UPDATE,DELETE ON steeltip.`'+table+'` TO %s@%s',(user,host))
                for table in INSERT_ONLY:
                    cursor.execute('GRANT INSERT ON steeltip.`'+table+'` TO %s@%s',(user,host))
        print('MariaDB project schema and restricted application account are ready.')
    finally:connection.close()

def mongo_admin(settings):
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure
    uri='mongodb://127.0.0.1:'+str(settings['mongo_port'])
    client=MongoClient(uri,serverSelectionTimeoutMS=5000)
    try:
        # ping alone is allowed even when authentication is required.
        client.steeltip.command('usersInfo',1)
        return client
    except OperationFailure as error:
        client.close()
        if error.code!=13:raise
    print('\nMongoDB has authentication enabled. Enter a database administrator account locally.')
    user=input('MongoDB administrator username: ').strip()
    auth_source=input('Authentication database [admin]: ').strip() or 'admin'
    password=getpass.getpass('MongoDB administrator password (hidden): ')
    client=MongoClient(uri,username=user,password=password,authSource=auth_source,serverSelectionTimeoutMS=5000)
    client.steeltip.command('usersInfo',1)
    return client

def setup_mongo(settings):
    schema=json.loads((ROOT/'mongo'/'validators.json').read_text(encoding='utf-8'))
    client=mongo_admin(settings)
    try:
        db=client.steeltip;existing=set(db.list_collection_names())
        for name,options in schema['collections'].items():
            if name not in existing:db.create_collection(name,**options)
            else:
                actual=db[name].options()
                if (actual.get('validator')!=options['validator'] or actual.get('validationLevel','strict')!='strict'
                        or actual.get('validationAction','error')!='error'):
                    raise RuntimeError('Existing MongoDB collection '+name+' has different validation settings. Existing data are preserved; no validator was overwritten.')
        for index in schema['indexes']:
            db[index['collection']].create_index(list(index['keys'].items()),**index['options'])
        role_info=db.command('rolesInfo',settings['mongo_role'])
        if not role_info['roles']:
            role=dict(schema['role']);role['role']=settings['mongo_role'];db.command('createRole',role.pop('role'),**role)
        if not db.command('usersInfo',settings['mongo_user'])['users']:
            db.command('createUser',settings['mongo_user'],pwd=settings['mongo_password'],roles=[{'role':settings['mongo_role'],'db':'steeltip'}])
        print('MongoDB validators, indexes and restricted application account are ready.')
    finally:client.close()

def verify_connections(settings):
    import pymysql
    from pymongo import MongoClient
    e=settings['environment']
    c=pymysql.connect(host='127.0.0.1',port=settings['sql_port'],user=e['SQL_USER'],password=e['SQL_PASSWORD'],database='steeltip',connect_timeout=5)
    try:
        with c.cursor() as cursor:cursor.execute('SELECT COUNT(*) FROM users');cursor.fetchone()
    finally:c.close()
    client=MongoClient(e['MONGO_URI'],serverSelectionTimeoutMS=5000)
    try:client.steeltip.revisions.find_one({}, {'_id':1})
    finally:client.close()

def prepare_settings(sql_port=3306,mongo_port=27017):
    if SETTINGS.exists():
        settings=json.loads(SETTINGS.read_text(encoding='utf-8'))
        if settings.get('format')!=1:raise RuntimeError('Unknown native-settings format. The configuration was preserved.')
        if (settings['sql_port'],settings['mongo_port'])!=(sql_port,mongo_port):
            raise RuntimeError('Native settings already use different database ports. Preserve that configuration and launch with its port values.')
        if settings.get('setup_complete'):
            verify_connections(settings);return settings
        print('Resuming the existing native setup without changing its generated passwords.')
    else:
        settings=fresh_settings(sql_port,mongo_port);save_settings(settings)
        print('Native connection settings created in runtime/native-settings.json.')
    setup_sql(settings);setup_mongo(settings);verify_connections(settings)
    settings['setup_complete']=True;save_settings(settings)
    return settings

def main():
    parser=argparse.ArgumentParser(description='SteelTip using local Windows MariaDB and MongoDB')
    parser.add_argument('--sql-port',type=int,default=3306);parser.add_argument('--mongo-port',type=int,default=27017)
    parser.add_argument('--port',type=int,default=8000);parser.add_argument('--setup-only',action='store_true')
    parser.add_argument('--host',default='127.0.0.1',choices=['127.0.0.1','0.0.0.0'],help='Use 0.0.0.0 for the optional same-Wi-Fi phone demonstration')
    args=parser.parse_args()
    try:
        if not args.setup_only and port_open(args.port):
            raise RuntimeError('Web port '+str(args.port)+' is already in use. Stop START_DEMO with Ctrl+C, or choose another --port.')
        for name,port in [('MariaDB',args.sql_port),('MongoDB',args.mongo_port)]:
            if not port_open(port):raise RuntimeError(name+' is not responding on local port '+str(port)+'. Start its Windows service first.')
        settings=prepare_settings(args.sql_port,args.mongo_port)
        print('\nNative database connections verified. This is real MariaDB + MongoDB mode.')
        print('Sign-in username: organiser')
        print('Website passwords in native-settings.json initialise NEW accounts only.')
        print('For an existing account, use its saved password or run RESET_WEBSITE_PASSWORD.bat.')
        if args.setup_only:return 0
        os.environ.update(settings['environment'])
        from .server import create_application,fastapi_application
        import uvicorn
        print('Preparing the synthetic dataset. First startup may take a little while...',flush=True)
        application=create_application(live=True)
        from .service import password_hash
        import hmac
        existing=application.r.one('users',username='organiser')['password_hash']
        configured=settings['environment']['ORGANISER_PASSWORD']
        if not hmac.compare_digest(password_hash(configured,existing.split(':')[0]),existing):
            print('NOTICE: the configured organiser password differs from the EXISTING MariaDB account. Run RESET_WEBSITE_PASSWORD.bat if forgotten.',flush=True)
        print('Open http://127.0.0.1:'+str(args.port)+' and check the Database mode banner.',flush=True)
        if args.host=='0.0.0.0':print('Phone mode: use this laptop Wi-Fi IPv4 address with port '+str(args.port)+' from the same private network.',flush=True)
        uvicorn.run(fastapi_application(application),host=args.host,port=args.port)
        return 0
    except KeyboardInterrupt:return 0
    except ImportError:
        print('Required Python packages are missing. Run START_NATIVE_DATABASE_APP.bat to install requirements.');return 1
    except Exception as error:
        print('Native startup could not complete: '+str(error));print('Existing records and administrator passwords have not been replaced.');return 1

if __name__=='__main__':raise SystemExit(main())
