import os
import sys
import traceback

# Windows fix for asyncio (needed by telethon.sync internally)
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auth_log.txt')

def log(msg):
    print(msg, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

try:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    env = dict(os.environ)  # start from real env
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env.setdefault(k.strip(), v.strip())  # env vars take priority

    API_ID   = int(env['API_ID'])
    API_HASH = env['API_HASH']
    TG_PHONE = env['TG_PHONE']
    # В Docker сессии живут в /app/sessions, локально — рядом со скриптом
    SESSION  = env.get('SESSION_PATH',
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sessions', 'sadcat_session'))

    os.makedirs(os.path.dirname(SESSION), exist_ok=True)
    log(f'SESSION: {SESSION}')

    # telethon.sync — полностью синхронный API, не требует asyncio.run()
    from telethon.sync import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    log('Telethon sync imported OK')

    client = TelegramClient(SESSION, API_ID, API_HASH)
    HASH_FILE = SESSION + '.codehash'
    try:
        client.connect()
        log('Client connected!')

        if client.is_user_authorized():
            me = client.get_me()
            log(f'Already authorized: {me.first_name} (@{me.username})')
            sys.exit(0)

        if len(sys.argv) < 2:
            # Шаг 1 — запросить код, сохранить hash в файл
            result = client.send_code_request(TG_PHONE)
            with open(HASH_FILE, 'w') as hf:
                hf.write(result.phone_code_hash)
            log(f'Code sent to {TG_PHONE}!')
            log(f'Now run: python auth_tg.py <CODE>')
        else:
            # Шаг 2 — войти с кодом, читаем hash из файла
            code = sys.argv[1].strip()
            if not os.path.exists(HASH_FILE):
                log('No hash file. Requesting new code first...')
                result = client.send_code_request(TG_PHONE)
                with open(HASH_FILE, 'w') as hf:
                    hf.write(result.phone_code_hash)
                log(f'New code sent to {TG_PHONE}! Run again with the new code.')
                sys.exit(0)
            with open(HASH_FILE, 'r') as hf:
                phone_code_hash = hf.read().strip()
            log(f'Signing in with code {code}...')
            try:
                client.sign_in(TG_PHONE, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                log('2FA required!')
                pwd = sys.argv[2] if len(sys.argv) > 2 else input('2FA: ')
                client.sign_in(password=pwd)
            try:
                os.remove(HASH_FILE)
            except Exception:
                pass
            me = client.get_me()
            log(f'SUCCESS! {me.first_name} (@{me.username})')
            log(f'Session: {SESSION}.session')
    finally:
        client.disconnect()

except Exception as e:
    log(f'ERROR: {e}')
    log(traceback.format_exc())
