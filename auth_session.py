"""One-time Telethon session auth — run once, then delete this file."""
import asyncio, os, sys
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

API_ID   = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
PHONE    = os.environ['TG_PHONE']
CODE     = sys.argv[1] if len(sys.argv) > 1 else input("Enter code: ")

SESSION = os.path.join(os.path.dirname(__file__), 'sessions', 'sadcat_session')
os.makedirs(os.path.dirname(SESSION), exist_ok=True)

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        # Send code request and sign in with provided code
        await client.send_code_request(PHONE)
        await client.sign_in(PHONE, CODE)

    me = await client.get_me()
    print(f"✅ Authorized as: {me.first_name} (@{me.username})")
    await client.disconnect()
    print(f"Session saved to: {SESSION}.session")

asyncio.run(main())
