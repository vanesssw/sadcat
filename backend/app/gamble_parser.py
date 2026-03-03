"""
Gamble channel parser.
Scans t.me/sadcatgamble for messages containing Solana contract addresses,
then enriches them with DexScreener price/mcap data.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import httpx

from app.entity_cache import get_cached_entity

logger = logging.getLogger(__name__)

CHANNEL = "sadcatgamble"
_channel_entity = None  # cached to avoid ResolveUsernameRequest every call
SCAN_DAYS = 30
DAYS_LIVE = 3
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"
PUMPFUN_URL     = "https://frontend-api.pump.fun/coins/{}"
HELIUS_URL      = "https://mainnet.helius-rpc.com/?api-key=144afcb1-245e-4ef2-a75f-e8079b65f988"
JUPITER_PRICE_URL = "https://price.jup.ag/v4/price?ids={}"

# Solana CA: exactly 43-44 base58 chars, NOT preceded by / or = (inside URL path/param)
SOL_CA_RE = re.compile(r'(?<![/=&?#])\b([1-9A-HJ-NP-Za-km-z]{43,44})\b')

# Pump.fun addresses are always 44 chars ending in 'pump'
PUMPFUN_CA_RE = re.compile(r'\b([1-9A-HJ-NP-Za-km-z]{40,43}pump)\b')

# Well-known program/token addresses to skip
EXCLUDE_ADDRS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "11111111111111111111111111111111",
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJe1bsW",
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",
    "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin",
    "SysvarRent111111111111111111111111111111111",
    "SysvarC1ock11111111111111111111111111111111",
    "ComputeBudget111111111111111111111111111111",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJejB",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP",
    "RVKd61ztZW9GUwhRbbLoYVRE5Xf1B2tVscKqwZqXgEr",
}


async def scan_channel_calls(client) -> List[Dict[str, Any]]:
    """
    Iterate recent messages in sadcatgamble, extract messages containing Solana CAs.
    Returns list of {msg_id, msg_date, msg_text, ca_address}.
    """
    results: List[Dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=SCAN_DAYS)

    global _channel_entity
    if _channel_entity is None:
        try:
            _channel_entity = await get_cached_entity(client, CHANNEL)
        except Exception as exc:
            logger.error("Cannot get channel %s: %s", CHANNEL, exc)
            return []
    channel = _channel_entity

    seen_msgs: set = set()

    async for msg in client.iter_messages(channel, limit=1000):
        if not msg.raw_text:
            continue
        if msg.date < cutoff:
            break
        if msg.id in seen_msgs:
            continue

        text = msg.raw_text

        # Try standard 43-44 char Solana CA first
        matches = SOL_CA_RE.findall(text)
        # Also try pump.fun 44-char addresses ending in 'pump'
        pump_matches = PUMPFUN_CA_RE.findall(text)
        all_matches = matches + [m for m in pump_matches if m not in matches]

        for ca in all_matches:
            if ca in EXCLUDE_ADDRS:
                continue
            seen_msgs.add(msg.id)
            results.append({
                "msg_id": msg.id,
                "msg_date": msg.date,
                "msg_text": msg.raw_text[:800],
                "ca_address": ca,
            })
            break  # one CA per message

    logger.info("Found %d messages with Solana CAs in #%s", len(results), CHANNEL)
    return results


async def fetch_dexscreener(ca: str, http: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    """Fetch token data from DexScreener API."""
    try:
        resp = await http.get(DEXSCREENER_URL.format(ca), timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        pairs = data.get("pairs") or []

        # Prefer Solana pairs; fall back to any
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        chosen = sol_pairs or pairs
        if not chosen:
            # No DEX pair — try pump.fun metadata
            return await fetch_pumpfun_meta(ca, http)

        # Pick pair with highest liquidity
        best = max(chosen, key=lambda p: float(p.get("liquidity", {}).get("usd") or 0))
        base = best.get("baseToken", {})

        pc = best.get("priceChange") or {}
        return {
            "token_name": base.get("name"),
            "token_symbol": base.get("symbol"),
            "price_usd": _f(best.get("priceUsd")),
            "fdv": _f(best.get("fdv")),
            "volume_24h": _f(best.get("volume", {}).get("h24")),
            "liquidity_usd": _f(best.get("liquidity", {}).get("usd")),
            "price_change_24h": _f(pc.get("h24")),
            "price_change_h6":  pc.get("h6"),
            "price_change_h1":  pc.get("h1"),
            "price_change_m5":  pc.get("m5"),
            "dex_url": best.get("url"),
            "pair_address": best.get("pairAddress"),
        }
    except Exception as exc:
        logger.debug("DexScreener error for %s: %s", ca, exc)
        return None


async def fetch_pumpfun_meta(ca: str, http: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    """
    Fallback for tokens without a DEX pair.
    1. Helius DAS getAsset  →  token name / symbol
    2. Jupiter Price API    →  current price / market cap
    """
    # --- Step 1: onchain metadata via Helius ---
    name = symbol = None
    try:
        resp = await http.post(
            HELIUS_URL,
            json={"jsonrpc": "2.0", "id": "1", "method": "getAsset", "params": {"id": ca}},
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            content = result.get("content", {})
            meta = content.get("metadata", {})
            name   = meta.get("name") or result.get("name")
            symbol = meta.get("symbol") or result.get("symbol")
    except Exception as exc:
        logger.debug("Helius getAsset error for %s: %s", ca, exc)

    if not name and not symbol:
        return None                # completely unknown token — skip

    # --- Step 2: price via Jupiter ---
    price_usd = 0.0
    market_cap = 0.0
    try:
        resp2 = await http.get(JUPITER_PRICE_URL.format(ca), timeout=8)
        if resp2.status_code == 200:
            jdata = resp2.json().get("data", {}).get(ca, {})
            price_usd = _f(jdata.get("price"))
            # Jupiter doesn't give mcap; leave as 0
    except Exception as exc:
        logger.debug("Jupiter price error for %s: %s", ca, exc)

    logger.info("No-pair meta for %s: name=%s symbol=%s price=%.8f", ca, name, symbol, price_usd)
    return {
        "token_name":       name or symbol,
        "token_symbol":     symbol or name,
        "price_usd":        price_usd,
        "fdv":              market_cap,
        "volume_24h":       0.0,
        "liquidity_usd":    0.0,
        "price_change_24h": 0.0,
        "price_change_h6":  None,
        "price_change_h1":  None,
        "price_change_m5":  None,
        "dex_url":          f"https://pump.fun/{ca}",
        "pair_address":     None,
        "is_pumpfun":       True,
    }


GECKO_OHLCV_URL = (
    "https://api.geckoterminal.com/api/v2/networks/solana/pools"
    "/{pair_address}/ohlcv/hour?aggregate=1&before_timestamp={ts_end}&limit=72&token=base"
)


async def fetch_ohlcv_ath_atl(
    pair_address: str,
    msg_date: datetime,
    http: httpx.AsyncClient,
) -> Optional[Dict[str, Any]]:
    """
    Fetch hourly OHLCV from GeckoTerminal for the 3-day window after the call.
    Returns dict with keys: price_at_call, ath_x, min_x, or None on failure.

    Window: [msg_date  ..  msg_date + 3 days]
    We request 72 hourly candles ending at msg_date + 3 days.
    """
    if not pair_address:
        return None

    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=timezone.utc)

    window_end   = msg_date + timedelta(days=DAYS_LIVE)
    window_start = msg_date
    ts_end = int(window_end.timestamp())

    try:
        url = GECKO_OHLCV_URL.format(pair_address=pair_address, ts_end=ts_end)
        resp = await http.get(url, timeout=15, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            logger.debug("GeckoTerminal OHLCV %s status=%s", pair_address, resp.status_code)
            return None

        data = resp.json()
        candles = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
        # Each candle: [unix_timestamp_ms_or_s, open, high, low, close, volume]
        if not candles:
            return None

        # Normalise timestamps to seconds
        def ts(c):
            t = c[0]
            return t / 1000 if t > 1e10 else t

        ts_start = window_start.timestamp()

        # Filter to the 3-day window
        window_candles = [c for c in candles if ts_start <= ts(c) <= ts_end]
        if not window_candles:
            # Fallback: use all returned (closest available)
            window_candles = candles

        highs  = [float(c[2]) for c in window_candles if c[2]]
        lows   = [float(c[3]) for c in window_candles if c[3]]
        # Price at call = open of the candle closest to msg_date
        sorted_candles = sorted(window_candles, key=lambda c: abs(ts(c) - window_start.timestamp()))
        price_at_call  = float(sorted_candles[0][1]) if sorted_candles else None   # open

        if not price_at_call or price_at_call <= 0 or not highs or not lows:
            return None

        ath_price = max(highs)
        atl_price = min(lows)

        return {
            "price_at_call": price_at_call,
            "ath_x": ath_price / price_at_call,
            "min_x": atl_price / price_at_call,
        }
    except Exception as exc:
        logger.debug("GeckoTerminal OHLCV error for %s: %s", pair_address, exc)
        return None


def _f(val) -> float:
    """Safe float conversion."""
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def is_live(msg_date: datetime) -> bool:
    """Returns True if the call was made within the last DAYS_LIVE days."""
    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - msg_date).days < DAYS_LIVE
