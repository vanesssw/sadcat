"""
SadCat Gamble — Backend API
FastAPI + Telethon + PostgreSQL
"""
import hashlib as _hashlib
import json as _json_std
import logging
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete, text

from app.config import settings
from app.database import engine, AsyncSessionLocal, Base
from app.models import LeaderboardEntry, ParseLog, RefLeaderboardEntry, GambleCall, WheelSpin, VerificationState
from app.telegram_parser import telegram_parser
from app.routers import leaderboard, contest
from app.routers import refleaderboard
from app.routers import gamble as gamble_router
from app.routers import verification
from app.gamble_parser import scan_channel_calls, fetch_dexscreener, is_live as call_is_live, fetch_ohlcv_ath_atl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# ── Wheel state (in-memory, shared across all clients) ────────────────────────
WHEEL_SPIN_SECONDS = 5 * 60

_SEG_COLORS = [
    '#0066ff','#00ccff','#9900ff','#ff6600','#00cc44',
    '#ff0066','#ffcc00','#00ffcc','#ff3300','#6600ff',
    '#00ff66','#ff9900','#3366ff','#ff0099','#33ff00',
    '#ff3366','#00ff99','#cc00ff','#ff9966','#0099ff',
]

_wheel_state: dict = {
    "winner_username": None,
    "winner_name":     None,
    "winner_avatar":   None,   # base64 string or null
    "winner_color":    None,
    "winner_tickets":  None,
    "winner_chance":   None,
    "winner_ticket":   None,
    "total_tickets":   None,
    "randorg_url":     None,
    "randorg_serial":  None,   # signed API serial number
    "randorg_sig":     None,   # first 16 chars of signature
    "randorg_signed":  None,   # full {random, signature} object for verification
    "next_spins_at":   int((_time.time() + WHEEL_SPIN_SECONDS) * 1000),  # unix ms
}


async def _get_random_org_ticket(total: int) -> tuple:
    """Get a random integer 1..total from random.org Signed API.
    Returns (ticket, serial, signature, random_obj).
    Raises RuntimeError if API key is not configured or request fails.
    No fallback to local random — a failed draw is better than an unverifiable one.
    """
    api_key = settings.random_org_api_key
    if not api_key:
        raise RuntimeError("RANDOM_ORG_API_KEY is not configured")

    payload = {
        "jsonrpc": "2.0",
        "method": "generateSignedIntegers",
        "params": {
            "apiKey": api_key,
            "n": 1,
            "min": 1,
            "max": total,
            "replacement": True,
        },
        "id": 1,
    }
    import httpx as _httpx
    async with _httpx.AsyncClient(timeout=10) as _http:
        resp = await _http.post(
            "https://api.random.org/json-rpc/4/invoke",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise RuntimeError(f"random.org error: {data['error']}")

    result = data["result"]
    ticket    = result["random"]["data"][0]
    serial    = result["random"]["serialNumber"]
    signature = result["signature"]
    random_obj = result["random"]
    logger.info("random.org SIGNED ticket: %d / %d (serial=%s)", ticket, total, serial)
    return ticket, serial, signature, random_obj


# Advisory lock key — any stable 64-bit int unique to this app
_WHEEL_ADVISORY_KEY = 7339475247


def _participants_hash(participants: list) -> str:
    """sha256 of canonical sorted JSON of participants (name + tickets only)."""
    canonical = _json_std.dumps(
        [{"name": p["name"], "tickets": p["tickets"]} for p in participants],
        sort_keys=True, separators=(",", ":")
    )
    return _hashlib.sha256(canonical.encode()).hexdigest()


def _wheel_state_from_spin(spin: WheelSpin, next_at_ms: int = 0) -> dict:
    """Convert a WheelSpin ORM row to the _wheel_state dict format.
    next_at_ms — override for next_spins_at (unix ms). If 0, compute from spin.created_at.
    """
    if next_at_ms <= 0:
        next_at_ms = int((spin.created_at.timestamp() + WHEEL_SPIN_SECONDS) * 1000)
    return {
        "winner_username": spin.winner_username,
        "winner_name":     spin.winner_name,
        "winner_avatar":   spin.winner_avatar,
        "winner_color":    spin.winner_color,
        "winner_tickets":  spin.winner_tickets,
        "winner_chance":   spin.winner_chance,
        "winner_ticket":   spin.winning_ticket,
        "total_tickets":   spin.total_tickets,
        "randorg_url":     "/verify",
        "randorg_serial":  spin.rand_serial,
        "randorg_sig":     spin.rand_signature[:16] if spin.rand_signature else None,
        "randorg_signed":  {"random": spin.rand_random, "signature": spin.rand_signature}
                           if spin.rand_random else None,
        "wheel_version_hash": spin.wheel_version_hash,
        "spin_id":         spin.id,
        "verify_link":     f"/api/wheel/verify/{spin.id}",
        "winner_range_start": spin.winner_range_start,
        "winner_range_end":   spin.winner_range_end,
        "spin_at":         int(spin.created_at.timestamp() * 1000) if spin.created_at else None,
        "next_spins_at":   next_at_ms,
    }


async def _load_wheel_state_from_db():
    """Load last successful spin from DB into _wheel_state."""
    global _wheel_state
    try:
        async with AsyncSessionLocal() as db:
            spin = (await db.execute(
                select(WheelSpin)
                .where(WheelSpin.status == "ok")
                .order_by(WheelSpin.id.desc())
                .limit(1)
            )).scalars().first()
        if spin:
            _wheel_state = _wheel_state_from_spin(
                spin,
                next_at_ms=int((_time.time() + WHEEL_SPIN_SECONDS) * 1000),
            )
            logger.info("Loaded last wheel spin #%d from DB (winner=%s)", spin.id, spin.winner_name)
        else:
            logger.info("No previous wheel spin in DB, will wait for first scheduler tick")
    except Exception as exc:
        logger.warning("Could not load wheel state from DB: %s", exc)


async def do_wheel_spin():
    """Pick a weighted-random winner from the leaderboard and persist to DB.

    Uses pg_try_advisory_xact_lock to prevent concurrent spins when running
    multiple workers or containers.
    No fallback to local random — if random.org is unavailable the spin is
    recorded as status='failed' and retried on the next scheduler tick.
    """
    global _wheel_state
    async with AsyncSessionLocal() as db:
        # ── 1. Advisory lock ─────────────────────────────────────────────────
        locked = (await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:k)").bindparams(k=_WHEEL_ADVISORY_KEY)
        )).scalar()
        if not locked:
            logger.warning("Wheel spin skipped: another instance holds the lock")
            return

        try:
            # ── 2. Load leaderboard ──────────────────────────────────────────
            rows = (await db.execute(
                select(LeaderboardEntry)
                .order_by(LeaderboardEntry.rank)
                .limit(20)
            )).scalars().all()

            if not rows:
                logger.warning("Wheel spin skipped: leaderboard is empty")
                _wheel_state["next_spins_at"] = int((_time.time() + WHEEL_SPIN_SECONDS) * 1000)
                return

            # ── 3. Build participants + hash ─────────────────────────────────
            max_score = rows[0].score or 1
            participants = []
            for i, e in enumerate(rows):
                tickets = max(1, round((e.score / max_score) * 100))
                participants.append({
                    "username": e.username,
                    "name":     e.display_name or e.username or f"Player {i+1}",
                    "tickets":  tickets,
                    "avatar":   e.avatar_b64,
                    "color":    _SEG_COLORS[i % len(_SEG_COLORS)],
                })

            wheel_hash = _participants_hash(participants)

            cumulative = 0
            ticket_ranges = []
            for p in participants:
                start = cumulative + 1
                end   = cumulative + p["tickets"]
                ticket_ranges.append((start, end, p))
                cumulative = end
            total = cumulative

            # ── 4. Draw from random.org (may raise) ──────────────────────────
            winning_ticket, rand_serial, rand_signature, rand_random = \
                await _get_random_org_ticket(total)
            winning_ticket = max(1, min(winning_ticket, total))

            # ── 5. Find winner ───────────────────────────────────────────────
            winner = participants[-1]
            winner_range_start, winner_range_end = 1, total
            for start, end, p in ticket_ranges:
                if start <= winning_ticket <= end:
                    winner = p
                    winner_range_start, winner_range_end = start, end
                    break

            chance = round(winner["tickets"] / total * 100, 1)
            now_utc = datetime.utcnow()

            # ── 6. Persist result ────────────────────────────────────────────
            spin = WheelSpin(
                created_at=now_utc,
                status="ok",
                wheel_version_hash=wheel_hash,
                total_tickets=total,
                participants_json=[{"name": p["name"], "username": p["username"],
                                    "tickets": p["tickets"], "color": p["color"]}
                                   for p in participants],
                winning_ticket=winning_ticket,
                winner_username=winner["username"],
                winner_name=winner["name"],
                winner_avatar=winner["avatar"],
                winner_color=winner["color"],
                winner_tickets=winner["tickets"],
                winner_chance=chance,
                winner_range_start=winner_range_start,
                winner_range_end=winner_range_end,
                rand_serial=rand_serial,
                rand_signature=rand_signature,
                rand_random=rand_random,
                verify_url="/verify",
            )
            db.add(spin)
            await db.commit()
            await db.refresh(spin)
            # lock released automatically on commit

            _wheel_state = _wheel_state_from_spin(spin)
            logger.info(
                "Wheel spin #%d: winner=%s ticket#%d/%d (%.1f%%) serial=%s hash=%s",
                spin.id, winner["name"], winning_ticket, total, chance,
                rand_serial, wheel_hash[:8],
            )

        except Exception as exc:
            await db.rollback()
            logger.exception("Wheel spin failed: %s", exc)
            # Record failed spin for audit
            try:
                async with AsyncSessionLocal() as err_db:
                    err_db.add(WheelSpin(
                        created_at=datetime.utcnow(),
                        status="failed",
                        error_msg=str(exc),
                    ))
                    await err_db.commit()
            except Exception:
                pass
            _wheel_state["next_spins_at"] = int((_time.time() + WHEEL_SPIN_SECONDS) * 1000)


async def update_ref_leaderboard():
    """Fetch clans leaderboard from Stream Bot HTTP API and save to DB."""
    logger.info("Starting ref leaderboard update...")
    async with AsyncSessionLocal() as db:
        try:
            entries = await _fetch_ref_leaderboard_http()

            if entries:
                from sqlalchemy import delete as sa_delete
                await db.execute(sa_delete(RefLeaderboardEntry))
                now = datetime.utcnow()
                for entry in entries:
                    db.add(
                        RefLeaderboardEntry(
                            rank=entry["rank"],
                            username=entry["username"],
                            display_name=entry.get("display_name"),
                            refs=entry.get("refs", 0),
                            avatar_b64=entry.get("avatar_b64"),
                            extra_data=entry.get("extra_data"),
                            updated_at=now,
                        )
                    )
                await db.commit()
                logger.info("Ref leaderboard updated: %d entries", len(entries))
            else:
                logger.warning("Ref leaderboard update returned 0 entries")
        except Exception as exc:
            await db.rollback()
            logger.exception("Ref leaderboard update failed: %s", exc)


def _estimate_mcap_at_call(msg_date, dex: dict) -> float:
    """
    Reconstruct the mcap at the time the Telegram call was posted.
    Picks the DexScreener priceChange interval whose timeframe best matches
    the age of the message:
      age <= 5 min  -> use m5
      age <= 1.5 h  -> use h1
      age <= 9 h    -> use h6
      age <= 72 h   -> use h24  (3-day calls window)
      age > 72 h    -> use h24 (best available; call window already passed)

    Formula: fdv_at_call = current_fdv / (1 + change_pct / 100)
    """
    from datetime import timezone as _tz
    current_fdv = dex.get("fdv") or 0
    if not current_fdv or current_fdv <= 0:
        return current_fdv

    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=_tz.utc)
    age_h = (datetime.now(_tz.utc) - msg_date).total_seconds() / 3600

    # Pick the interval closest to the call age
    if age_h <= 0.08:          # <5 min — essentially now
        return current_fdv
    elif age_h <= 0.5:
        interval = dex.get("price_change_m5")
    elif age_h <= 1.5:
        interval = dex.get("price_change_h1")
    elif age_h <= 9:
        interval = dex.get("price_change_h6")
    else:                       # older than 9h — h24 is the deepest we have
        interval = dex.get("price_change_24h")

    if interval is not None:
        try:
            factor = 1.0 + float(interval) / 100.0
            if factor > 0.001:
                return current_fdv / factor
        except (TypeError, ValueError):
            pass
    return current_fdv          # fallback: use current as baseline


def _ath_atl_from_dex(mcap_at_call: float, dex: dict):
    """
    Reconstruct multiple historical mcap snapshots from DexScreener
    priceChange intervals (m5 / h1 / h6 / h24) and return (ath_x, min_x).

    Logic:
      price_change_hN = (current/price_N_ago - 1) * 100
      => fdv_N_ago = current_fdv / (1 + change/100)
      => x_N_ago   = fdv_N_ago / mcap_at_call

    We take max of all candidates as ATH and min as ATL.
    """
    current_fdv = dex.get("fdv") or 0
    if not mcap_at_call or mcap_at_call <= 0 or current_fdv <= 0:
        return 1.0, 1.0

    current_x = current_fdv / mcap_at_call
    candidates = [current_x]

    for change_pct in [
        dex.get("price_change_m5"),
        dex.get("price_change_h1"),
        dex.get("price_change_h6"),
        dex.get("price_change_24h"),
    ]:
        if change_pct is None:
            continue
        try:
            factor = 1.0 + float(change_pct) / 100.0
            if factor > 0.001:            # sanity guard
                hist_fdv = current_fdv / factor
                hist_x   = hist_fdv / mcap_at_call
                if hist_x > 0:
                    candidates.append(hist_x)
        except (TypeError, ValueError):
            pass

    return max(candidates), min(candidates)


async def update_gamble_calls():
    """Scan sadcatgamble channel for Solana CAs and enrich with DexScreener data."""
    logger.info("Starting gamble calls update...")
    if not telegram_parser.client or not telegram_parser.client.is_connected():
        try:
            await telegram_parser.start()
        except Exception as exc:
            logger.error("Cannot start Telegram client for gamble: %s", exc)
            return

    try:
        channel_calls = await scan_channel_calls(telegram_parser.client)
    except Exception as exc:
        logger.exception("Channel scan failed: %s", exc)
        return

    if not channel_calls:
        logger.warning("No gamble calls found in channel")
        return

    import httpx
    from sqlalchemy import select as sa_select
    from datetime import datetime

    async with AsyncSessionLocal() as db:
        try:
            async with httpx.AsyncClient(timeout=12) as http:
                gecko_finalized = 0          # max finalized per cycle to respect rate limit
                MAX_GECKO_PER_CYCLE = 5

                for item in channel_calls:
                    msg_id = item["msg_id"]

                    # Check if already exists
                    existing = (await db.execute(
                        sa_select(GambleCall).where(GambleCall.msg_id == msg_id)
                    )).scalar_one_or_none()

                    dex = await fetch_dexscreener(item["ca_address"], http)
                    now = datetime.utcnow()
                    live = call_is_live(item["msg_date"])

                    if existing is None:
                        # New call — estimate price at call time via DexScreener intervals.
                        if dex and dex.get("fdv", 0) > 0:
                            mcap_at_call_est = _estimate_mcap_at_call(item["msg_date"], dex)
                            price_at_call_est = (
                                dex["price_usd"] * (mcap_at_call_est / dex["fdv"])
                                if dex["fdv"] > 0 else dex["price_usd"]
                            )
                            # Within 3-day window: seed ATH/ATL from priceChange intervals
                            if live:
                                ath_init, min_init = _ath_atl_from_dex(mcap_at_call_est, dex)
                            else:
                                ath_init, min_init = 1.0, 1.0
                        else:
                            mcap_at_call_est = None
                            price_at_call_est = None
                            ath_init, min_init = 1.0, 1.0
                        call = GambleCall(
                            msg_id=msg_id,
                            msg_date=item["msg_date"],
                            msg_text=item["msg_text"],
                            ca_address=item["ca_address"],
                            pair_address=dex.get("pair_address") if dex else None,
                            token_name=dex["token_name"] if dex else None,
                            token_symbol=dex["token_symbol"] if dex else None,
                            price_at_call=price_at_call_est,
                            mcap_at_call=mcap_at_call_est,
                            current_price=dex["price_usd"] if dex else None,
                            current_mcap=dex["fdv"] if dex else None,
                            ath_x=ath_init,
                            min_x=min_init,
                            ath_atl_final=False,
                            volume_24h=dex["volume_24h"] if dex else None,
                            liquidity_usd=dex["liquidity_usd"] if dex else None,
                            price_change_24h=dex["price_change_24h"] if dex else None,
                            dex_url=dex["dex_url"] if dex else None,
                            is_live=live,
                            updated_at=now,
                        )
                        db.add(call)
                    else:
                        # Always refresh current market data for display
                        if dex:
                            existing.current_price    = dex["price_usd"]
                            existing.current_mcap     = dex["fdv"]
                            existing.volume_24h       = dex["volume_24h"]
                            existing.liquidity_usd    = dex["liquidity_usd"]
                            existing.price_change_24h = dex["price_change_24h"]
                            # Only overwrite dex_url with pump.fun link if we have nothing better
                            if dex.get("dex_url"):
                                if not dex.get("is_pumpfun") or not existing.dex_url:
                                    existing.dex_url = dex["dex_url"]
                            if not existing.token_name:
                                existing.token_name   = dex["token_name"]
                                existing.token_symbol = dex["token_symbol"]
                            if not existing.pair_address:
                                existing.pair_address = dex.get("pair_address")

                        if existing.ath_atl_final:
                            # Already frozen from real historical data — skip
                            pass
                        elif live:
                            # Inside 3-day window — accumulate from real-time snapshots
                            if existing.mcap_at_call and existing.mcap_at_call > 0 \
                                    and dex and dex["fdv"] > 0:
                                new_ath, new_min = _ath_atl_from_dex(existing.mcap_at_call, dex)
                                existing.ath_x = max(existing.ath_x or 1.0, new_ath)
                                existing.min_x = min(
                                    existing.min_x if existing.min_x is not None else 1.0,
                                    new_min
                                )
                        else:
                            # 3-day window CLOSED, not yet finalized.
                            # Fetch real OHLCV from GeckoTerminal for [msg_date .. msg_date+3d].
                            # Limit to MAX_GECKO_PER_CYCLE per scheduler run.
                            pair_addr = existing.pair_address or (
                                dex.get("pair_address") if dex else None
                            )
                            if pair_addr and gecko_finalized < MAX_GECKO_PER_CYCLE:
                                import asyncio as _asyncio
                                await _asyncio.sleep(1.2)   # GeckoTerminal free tier: ~1 req/s
                                ohlcv = await fetch_ohlcv_ath_atl(
                                    pair_addr, existing.msg_date, http
                                )
                                if ohlcv:
                                    if ohlcv["price_at_call"] and ohlcv["price_at_call"] > 0:
                                        existing.price_at_call = ohlcv["price_at_call"]
                                    existing.ath_x = ohlcv["ath_x"]
                                    existing.min_x = ohlcv["min_x"]
                                    existing.ath_atl_final = True
                                    gecko_finalized += 1
                                    logger.info(
                                        "Finalized ATH/ATL for %s (msg %s): ath=%.3f atl=%.3f",
                                        existing.token_symbol or existing.ca_address,
                                        existing.msg_date.date(),
                                        ohlcv["ath_x"], ohlcv["min_x"],
                                    )
                                else:
                                    # GeckoTerminal unavailable — keep DexScreener snapshot
                                    if existing.mcap_at_call and existing.mcap_at_call > 0 \
                                            and dex and dex["fdv"] > 0:
                                        new_ath, new_min = _ath_atl_from_dex(
                                            existing.mcap_at_call, dex
                                        )
                                        existing.ath_x = max(existing.ath_x or 1.0, new_ath)
                                        existing.min_x = min(
                                            existing.min_x if existing.min_x is not None else 1.0,
                                            new_min
                                        )

                        existing.is_live = live
                        existing.updated_at = now

            await db.commit()
            logger.info("Gamble calls updated: %d entries", len(channel_calls))
        except Exception as exc:
            await db.rollback()
            logger.exception("Gamble calls update failed: %s", exc)


async def _fetch_leaderboard_http(limit: int = 100) -> list:
    """Fetch players leaderboard from Stream Bot HTTP API."""
    import httpx as _httpx
    url = f"{settings.stream_bot_url}/api/leaderboard/players"
    headers = {"Authorization": f"Bearer {settings.stream_bot_token}"}
    async with _httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={"limit": limit}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    result = []
    for item in data.get("leaderboard", []):
        display = item.get("first_name") or item.get("username", "")
        if item.get("last_name"):
            display = f"{display} {item['last_name']}".strip()
        result.append({
            "rank": item["rank"],
            "username": item.get("username", ""),
            "display_name": display,
            "score": item.get("points", 0),
            "avatar_b64": None,
        })
    return result


async def _fetch_ref_leaderboard_http(limit: int = 100) -> list:
    """Fetch clans leaderboard from Stream Bot HTTP API."""
    import httpx as _httpx
    url = f"{settings.stream_bot_url}/api/leaderboard/clans"
    headers = {"Authorization": f"Bearer {settings.stream_bot_token}"}
    async with _httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={"limit": limit}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    result = []
    for item in data.get("leaderboard", []):
        result.append({
            "rank": item["rank"],
            "username": item.get("owner_username", item.get("slug", "")),
            "display_name": item.get("name", ""),
            "refs": item.get("clan_points", 0),
            "avatar_b64": None,
        })
    return result


async def update_leaderboard():
    """Fetch leaderboard from Stream Bot HTTP API and save to DB."""
    logger.info("Starting leaderboard update...")
    async with AsyncSessionLocal() as db:
        try:
            entries = await _fetch_leaderboard_http()

            if entries:
                # Clear old data and insert fresh
                await db.execute(delete(LeaderboardEntry))
                now = datetime.utcnow()
                for entry in entries:
                    db.add(
                        LeaderboardEntry(
                            rank=entry["rank"],
                            username=entry["username"],
                            display_name=entry.get("display_name"),
                            score=entry["score"],
                            avatar_b64=entry.get("avatar_b64"),
                            extra_data=entry.get("extra_data"),
                            updated_at=now,
                        )
                    )
                log = ParseLog(
                    status="success",
                    entries_count=len(entries),
                    parsed_at=now,
                )
                db.add(log)
                await db.commit()
                logger.info("Leaderboard updated: %d entries", len(entries))
            else:
                log = ParseLog(
                    status="empty",
                    entries_count=0,
                    error_msg="Bot returned no parseable data",
                )
                db.add(log)
                await db.commit()
                logger.warning("Leaderboard update returned 0 entries")

        except Exception as exc:
            await db.rollback()
            log = ParseLog(
                status="error",
                entries_count=0,
                error_msg=str(exc),
            )
            async with AsyncSessionLocal() as log_db:
                log_db.add(log)
                await log_db.commit()
            logger.exception("Leaderboard update failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    # Create tables (idempotent, init.sql handles it too but belt+suspenders)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Connect Telegram client
    if getattr(settings, "enable_telegram", True):
        try:
            await telegram_parser.start()
            logger.info("Telegram client ready")
        except Exception as exc:
            logger.error("Could not start Telegram client: %s", exc)
    else:
        logger.info("Telegram client disabled")

    # Pre-populate avatar cache from DB so restart doesn't re-download 100 avatars
    try:
        async with AsyncSessionLocal() as _db:
            _rows = (await _db.execute(
                select(LeaderboardEntry.username, LeaderboardEntry.avatar_b64)
                .where(LeaderboardEntry.avatar_b64.isnot(None))
            )).all()
            _ref_rows = (await _db.execute(
                select(RefLeaderboardEntry.username, RefLeaderboardEntry.avatar_b64)
                .where(RefLeaderboardEntry.avatar_b64.isnot(None))
            )).all()
        avatar_map = {row[0]: row[1] for row in list(_rows) + list(_ref_rows)}
        telegram_parser.preload_avatar_cache(avatar_map)
    except Exception as exc:
        logger.warning("Could not preload avatar cache from DB: %s", exc)

    # Initial fetch
    await update_leaderboard()
    await update_ref_leaderboard()
    await update_gamble_calls()

    # Restore last wheel state from DB; spin immediately only if no history
    await _load_wheel_state_from_db()
    if _wheel_state.get("winner_name") is None:
        await do_wheel_spin()

    # Schedule periodic updates (staggered by 30s to avoid concurrent bot handlers)
    from datetime import datetime, timedelta
    now = datetime.now()
    scheduler.add_job(
        update_leaderboard,
        "interval",
        seconds=settings.leaderboard_update_interval,
        start_date=now + timedelta(seconds=settings.leaderboard_update_interval),
        id="leaderboard_update",
        replace_existing=True,
    )
    scheduler.add_job(
        update_ref_leaderboard,
        "interval",
        seconds=settings.leaderboard_update_interval,
        start_date=now + timedelta(seconds=settings.leaderboard_update_interval + 30),
        id="ref_leaderboard_update",
        replace_existing=True,
    )
    scheduler.add_job(
        update_gamble_calls,
        "interval",
        seconds=300,
        start_date=now + timedelta(seconds=60),
        id="gamble_calls_update",
        replace_existing=True,
    )
    # Compute next spin time: ensure it's always in the future
    raw_next = _wheel_state.get("next_spins_at", 0) / 1000
    if raw_next <= now.timestamp() + 5:
        # Already passed or within 5s — schedule from now
        next_spin_dt = now + timedelta(seconds=WHEEL_SPIN_SECONDS)
    else:
        next_spin_dt = datetime.fromtimestamp(raw_next)

    scheduler.add_job(
        do_wheel_spin,
        "interval",
        seconds=WHEEL_SPIN_SECONDS,
        start_date=next_spin_dt,
        misfire_grace_time=90,   # allow up to 90s late (event loop jitter)
        id="wheel_spin",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started, interval=%ds", settings.leaderboard_update_interval
    )

    yield

    # ---- Shutdown ----
    scheduler.shutdown(wait=False)
    try:
        await telegram_parser.stop()
    except Exception:
        pass
    await engine.dispose()
    logger.info("App shutdown complete")


app = FastAPI(
    title="SadCat Gamble API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(leaderboard.router)
app.include_router(contest.router)
app.include_router(refleaderboard.router)
app.include_router(gamble_router.router)
app.include_router(verification.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "sadcat-api"}


@app.get("/captcha")
async def captcha_page():
    """Отдает captcha.html с подставленным ключом"""
    from fastapi.responses import HTMLResponse
    
    # Читаем HTML файл из смонтированного volume
    html_path = "/app/frontend/captcha.html"
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # Подставляем ключ прямо в HTML
    html_content = html_content.replace(
        '<meta name="yandex-client-key" content="YANDEX_CLIENT_KEY_HERE" />',
        f'<meta name="yandex-client-key" content="{settings.yandex_smartcaptcha_client_key}" />',
    )
    
    return HTMLResponse(content=html_content)


@app.get("/api/wheel/state")
async def wheel_state_endpoint():
    """Return last successful wheel spin from DB (+ in-memory cache)."""
    # Always serve from in-memory cache (populated on spin / startup)
    # If cache is empty (edge case), try DB directly
    if _wheel_state.get("winner_name") is None:
        await _load_wheel_state_from_db()
    return _wheel_state


@app.get("/api/wheel/history")
async def wheel_history_endpoint(limit: int = 20):
    """Return last N wheel spins from DB for audit/history."""
    async with AsyncSessionLocal() as db:
        spins = (await db.execute(
            select(WheelSpin)
            .where(WheelSpin.status == "ok")
            .order_by(WheelSpin.id.desc())
            .limit(min(limit, 100))
        )).scalars().all()
    return [
        {
            "id":                 s.id,
            "created_at":         s.created_at.isoformat() if s.created_at else None,
            "winner_name":        s.winner_name,
            "winner_username":    s.winner_username,
            "winner_avatar":      s.winner_avatar,
            "winner_color":       s.winner_color,
            "winning_ticket":     s.winning_ticket,
            "total_tickets":      s.total_tickets,
            "winner_range_start": s.winner_range_start,
            "winner_range_end":   s.winner_range_end,
            "winner_chance":      s.winner_chance,
            "rand_serial":        s.rand_serial,
            "wheel_version_hash": s.wheel_version_hash,
            "verify_url":         f"/api/wheel/verify/{s.id}",
        }
        for s in spins
    ]


@app.post("/api/leaderboard/refresh")
async def manual_refresh():
    """Manually trigger a leaderboard refresh."""
    await update_leaderboard()
    return {"status": "refreshed"}


@app.post("/api/wheel/spin")
async def manual_wheel_spin():
    """Manually trigger a wheel spin (dev/admin use)."""
    await do_wheel_spin()
    return _wheel_state


@app.get("/api/wheel/verify/{spin_id}")
async def verify_spin_redirect(spin_id: int):
    """Redirect to random.org signature verification form for a given spin."""
    import base64 as _b64
    from urllib.parse import quote as _quote
    from fastapi.responses import RedirectResponse as _Redir

    async with AsyncSessionLocal() as db:
        spin = (await db.execute(
            select(WheelSpin).where(WheelSpin.id == spin_id)
        )).scalars().first()
    if not spin or spin.status != "ok" or not spin.rand_random:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Spin not found or no signed data")

    rand_json = _json_std.dumps(spin.rand_random, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    rand_b64  = _b64.b64encode(rand_json).decode("ascii")
    url = (
        "https://api.random.org/signatures/form?format=json"
        + "&random=" + _quote(rand_b64)
        + "&signature=" + _quote(spin.rand_signature)
    )
    return _Redir(url, status_code=302)


@app.get("/api/wheel/spin/{spin_id}")
async def get_spin_by_id(spin_id: int):
    """Return a single spin by ID — used by /verify?spin=N."""
    async with AsyncSessionLocal() as db:
        spin = (await db.execute(
            select(WheelSpin).where(WheelSpin.id == spin_id)
        )).scalars().first()
    if spin is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Spin not found")
    return {
        "id":                 spin.id,
        "created_at":         spin.created_at.isoformat() if spin.created_at else None,
        "status":             spin.status,
        "winner_name":        spin.winner_name,
        "winner_username":    spin.winner_username,
        "winner_avatar":      spin.winner_avatar,
        "winner_color":       spin.winner_color,
        "winner_tickets":     spin.winner_tickets,
        "winner_chance":      spin.winner_chance,
        "winning_ticket":     spin.winning_ticket,
        "winner_ticket":      spin.winning_ticket,
        "total_tickets":      spin.total_tickets,
        "winner_range_start": spin.winner_range_start,
        "winner_range_end":   spin.winner_range_end,
        "wheel_version_hash": spin.wheel_version_hash,
        "participants":       spin.participants_json,
        "rand_serial":        spin.rand_serial,
        "randorg_serial":     spin.rand_serial,
        "randorg_signed":     {"random": spin.rand_random, "signature": spin.rand_signature}
                              if spin.rand_random else None,
        "verify_link":        f"/api/wheel/verify/{spin.id}",
        "spin_id":            spin.id,
    }
