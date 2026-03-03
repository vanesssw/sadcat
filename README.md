# SadCat Gamble — Leaderboard Site

> Even if you are sad, remember that someone bought a pizza for bitcoins. meow :3

## Stack

| Layer     | Tech                        |
|-----------|-----------------------------|
| Frontend  | HTML / CSS / Vanilla JS     |
| Backend   | Python 3.12 + FastAPI       |
| Telegram  | Telethon (MTProto)          |
| DB        | PostgreSQL 16               |
| Container | Docker + docker-compose     |
| Proxy     | Nginx                       |

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials (already filled for sadcat)
```

### 2. First-time Telegram auth (important!)

Telethon needs to authorize your phone number once interactively.
Run this locally **before** starting Docker:

```bash
cd backend
pip install telethon python-dotenv
python - <<'EOF'
import asyncio, os
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv('../.env')
client = TelegramClient(
    'sadcat_session',
    int(os.environ['API_ID']),
    os.environ['API_HASH'],
)

async def main():
    await client.start(phone=os.environ['TG_PHONE'])
    print("Auth OK!")
    await client.disconnect()

asyncio.run(main())
EOF
```

Copy the generated session file into the Docker volume directory:

```bash
mkdir -p sessions
cp sadcat_session.session sessions/
```

### 3. Build & run

```bash
docker-compose up --build
```

Site available at: **http://localhost**

---

## API Endpoints

| Method | URL                          | Description               |
|--------|------------------------------|---------------------------|
| GET    | `/api/leaderboard`           | Get leaderboard entries   |
| POST   | `/api/leaderboard/refresh`   | Force re-parse from bot   |
| GET    | `/api/leaderboard/logs`      | Parse history logs        |
| GET    | `/api/contest`               | Active contest info       |
| GET    | `/api/health`                | Health check              |

---

## Leaderboard auto-parse

- On startup the backend sends `/leaderboard` to `@sadcat250bot` via Telethon
- Response is parsed with regex (see `backend/app/telegram_parser.py`)
- Automatically re-fetches every **5 minutes** (configurable via `LEADERBOARD_UPDATE_INTERVAL`)
- Frontend polls every 60 seconds and supports manual refresh

---

## Bot response format

The parser tries these patterns in order:

1. `1. @username — 1234`
2. `#1 username 1234`
3. `1 | username | 1234`

If your bot uses a different format, update `_parse_leaderboard_text()` in
`backend/app/telegram_parser.py` accordingly.

---

## Add contest info

Insert a row into the `contest_info` table:

```sql
INSERT INTO contest_info (title, description, prize_pool, start_date, end_date, is_active)
VALUES (
  'SadCat October Contest',
  'Top traders win big rewards!',
  '1000 SOL',
  '2025-10-01',
  '2025-10-31',
  true
);
```

---

NFA meow :3
