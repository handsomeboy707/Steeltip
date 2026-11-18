"""Generate new local secrets without printing or overwriting them."""
from pathlib import Path
import secrets
path=Path(__file__).resolve().parent/'.env'
if path.exists():
    print('.env already exists and has been preserved.')
else:
    sql,mongo=secrets.token_hex(24),secrets.token_hex(24)
    values={'SQL_PASSWORD':sql,'MONGO_APP_PASSWORD':mongo,'MARIADB_ROOT_PASSWORD':secrets.token_hex(24),
      'MONGO_ROOT_PASSWORD':secrets.token_hex(24),
      'MONGO_URI':f'mongodb://steeltip_app:{mongo}@mongodb:27017/steeltip?authSource=steeltip',
      'ORGANISER_PASSWORD':secrets.token_urlsafe(24),'SCORER_PASSWORD':secrets.token_urlsafe(24),
      'VIEWER_PASSWORD':secrets.token_urlsafe(24)}
    path.write_text(''.join(k+'='+v+'\n' for k,v in values.items()),encoding='utf-8')
    print('Created .env. Open this private file to read login passwords. Do not submit it.')
