"""Local administrator recovery; never treats settings edits as an account reset."""
import getpass
import json
from .native_setup import SETTINGS, save_settings
from .service import password_hash, uid, now


def reset_account(connection, username, password):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError('Use at least 12 characters for the website password')
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute('SELECT id FROM users WHERE username=%s FOR UPDATE', (username,))
            row = cursor.fetchone()
            if not row:
                raise ValueError('Website username not found; no account was created')
            user_id = row[0]
            cursor.execute('UPDATE users SET password_hash=%s WHERE id=%s', (password_hash(password), user_id))
            cursor.execute('DELETE FROM sessions WHERE user_id=%s', (user_id,))
            cursor.execute('INSERT INTO audits(id,user_id,action,entity_id,details,created_at) VALUES(%s,%s,%s,%s,%s,%s)',
                           (uid(), user_id, 'password_reset_local_admin', user_id, json.dumps({'method': 'local MariaDB administrator'}), now()))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def main():
    import pymysql
    if not SETTINGS.exists():
        print('Run START_NATIVE_DATABASE_APP.bat to configure this folder first.'); return 1
    settings = json.loads(SETTINGS.read_text(encoding='utf-8'))
    print('Reset a WEBSITE account. Existing competition records are preserved.')
    username = input('Website username [organiser]: ').strip() or 'organiser'
    admin = input('MariaDB administrator username [root]: ').strip() or 'root'
    admin_password = getpass.getpass('MariaDB administrator password (hidden): ')
    password = getpass.getpass('New website password, at least 12 characters (hidden): ')
    if password != getpass.getpass('Repeat new website password: '):
        print('Passwords differ. Nothing changed.'); return 1
    try:
        connection = pymysql.connect(host='127.0.0.1', port=settings['sql_port'], user=admin,
                                     password=admin_password, database='steeltip', charset='utf8mb4', connect_timeout=5)
        try: reset_account(connection, username, password)
        finally: connection.close()
    except Exception as error:
        print('Password reset failed: ' + str(error)); return 1
    print('Website password reset. Previous sessions have been signed out.')
    if username in ('organiser', 'scorer', 'viewer'):
        settings['environment'][username.upper() + '_PASSWORD'] = password
        try: save_settings(settings)
        except OSError:
            print('The DATABASE reset succeeded, but settings could not be saved. Sign in with your new password; update the matching website-password field locally.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
