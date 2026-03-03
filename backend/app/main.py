"""
SadCat Gamble — Backend API
FastAPI + Telethon + PostgreSQL
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete, text

from app.config import settings
from app.database import engine, AsyncSessionLocal, Base
from app.models import LeaderboardEntry, ParseLog, RefLeaderboardEntry, GambleCall
from app.telegram_parser import telegram_parser
from app.routers import leaderboard, contest
from app.routers import refleaderboard
from app.routers import gamble as gamble_router
from app.gamble_parser import scan_channel_calls, fetch_dexscreener, is_live as call_is_live, fetch_ohlcv_ath_atl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def update_ref_leaderboard():
    """Fetch ref leaderboard from Telegram bot and save to DB."""
    logger.info("Starting ref leaderboard update...")
    async with AsyncSessionLocal() as db:
        try:
            entries = await telegram_parser.fetch_ref_leaderboard()

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


async def update_leaderboard():
    """Fetch leaderboard from Telegram bot and save to DB."""
    logger.info("Starting leaderboard update...")
    async with AsyncSessionLocal() as db:
        try:
            entries = await telegram_parser.fetch_leaderboard()

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
    try:
        await telegram_parser.start()
        logger.info("Telegram client ready")
    except Exception as exc:
        logger.error("Could not start Telegram client: %s", exc)

    # Initial fetch
    await update_leaderboard()
    await update_ref_leaderboard()
    await update_gamble_calls()

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
    scheduler.start()
    logger.info(
        "Scheduler started, interval=%ds", settings.leaderboard_update_interval
    )

    yield

    # ---- Shutdown ----
    scheduler.shutdown(wait=False)
    await telegram_parser.stop()
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "sadcat-api"}


@app.post("/api/leaderboard/refresh")
async def manual_refresh():
    """Manually trigger a leaderboard refresh."""
    await update_leaderboard()
    return {"status": "refreshed"}
