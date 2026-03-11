"""
Run inside container:
  docker exec -it sadcat-backend-1 python3 /app/auth_tg.py
It will request the code AND wait for you to type it — all in one connection.
"""
import os
import sys
import asyncio
import traceback


def load_env():
    env = dict(os.environ)
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env.setdefault(k.strip(), v.strip())
    return env


async def main():
    env = load_env()
    API_ID   = int(env['API_ID'])
    API_HASH = env['API_HASH']
    TG_PHONE = env['TG_PHONE']
    SESSION  = env.get('SESSION_PATH', '/app/sessions/sadcat_session')

    os.makedirs(os.path.dirname(SESSION), exist_ok=True)
    print(f'[*] Session: {SESSION}', flush=True)

    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    print('[*] Connected to Telegram', flush=True)

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f'[OK] Already authorized: {me.first_name} (@{me.username})', flush=True)
        await client.disconnect()
        return

    # Send code and keep connection alive — hash stays valid
    print(f'[*] Sending code to {TG_PHONE} ...', flush=True)
    result = await client.send_code_request(TG_PHONE)
    phone_code_hash = result.phone_code_hash
    print(f'[*] Code sent! Check Telegram app on your phone.', flush=True)

    # Read code from stdin (works with docker exec -it)
    code = input('[>] Enter the code: ').strip()

    try:
        await client.sign_in(TG_PHONE, code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        print('[*] 2FA is enabled', flush=True)
        pwd = input('[>] Enter 2FA password: ').strip()
        await client.sign_in(password=pwd)

    me = await client.get_me()
    print(f'\n[SUCCESS] Authorized as: {me.first_name} (@{me.username})', flush=True)
    print(f'[*] Session saved to: {SESSION}.session', flush=True)
    print('[*] Now restart backend: docker-compose restart backend', flush=True)
    await client.disconnect()


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print('\n[!] Cancelled', flush=True)
except Exception as e:
    print(f'[ERROR] {e}', flush=True)
    print(traceback.format_exc(), flush=True)

