"""
Telegram parser using Telethon.
Sends /leaderboard to the bot and parses the response.
"""
import asyncio
import base64
import io
import logging
import re
from datetime import datetime
from typing import List, Dict, Any

from telethon import TelegramClient, events
from telethon.tl.types import Message

from app.config import settings
from app.entity_cache import get_cached_entity

logger = logging.getLogger(__name__)

# Telethon session stored inside container volume
SESSION_NAME = "/app/sessions/sadcat_session"


class TelegramParser:
    def __init__(self):
        self.client: TelegramClient | None = None
        self._avatar_cache: Dict[str, str] = {}  # username -> base64
        self._fetch_lock = asyncio.Lock()  # prevent concurrent bot message handlers
        self._bot_entity = None  # cached to avoid ResolveUsernameRequest every call

    async def start(self):
        """Initialize and connect the Telegram client."""
        self.client = TelegramClient(
            SESSION_NAME,
            settings.api_id,
            settings.api_hash,
        )
        await self.client.start(phone=settings.tg_phone)
        logger.info("Telegram client connected")

    async def stop(self):
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Telegram client disconnected")

    async def fetch_ref_leaderboard(self) -> List[Dict[str, Any]]:
        """Send /refleaderboard to the bot and parse the response."""
        async with self._fetch_lock:
            return await self._do_fetch_ref_leaderboard()

    async def _do_fetch_ref_leaderboard(self) -> List[Dict[str, Any]]:
        if not self.client or not self.client.is_connected():
            await self.start()

        if self._bot_entity is None:
            try:
                self._bot_entity = await get_cached_entity(self.client, settings.bot_username)
            except Exception as exc:
                logger.error("Cannot resolve bot entity: %s", exc)
                return []
        bot = self._bot_entity

        response_text = None
        response_event = asyncio.Event()

        @self.client.on(events.NewMessage(from_users=bot))
        async def _handler(event: events.NewMessage.Event):
            nonlocal response_text
            response_text = event.raw_text
            response_event.set()

        try:
            await self.client.send_message(bot, "/refleaderboard")
            try:
                await asyncio.wait_for(response_event.wait(), timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Bot did not respond to /refleaderboard in time")
                return []
        finally:
            self.client.remove_event_handler(_handler)

        if not response_text:
            return []

        entries = self._parse_ref_leaderboard_text(response_text)

        for entry in entries:
            entry["refs"] = entry.pop("score", 0)
            entry["avatar_b64"] = await self._get_avatar(entry["username"])

        return entries

    async def fetch_leaderboard(self) -> List[Dict[str, Any]]:
        """
        Send /leaderboard to the bot and parse the response.
        Returns a list of dicts with rank, username, display_name, score, avatar_b64.
        """
        async with self._fetch_lock:
            return await self._do_fetch_leaderboard()

    async def _do_fetch_leaderboard(self) -> List[Dict[str, Any]]:
        """
        Internal fetch — called under lock.
        """
        if not self.client or not self.client.is_connected():
            await self.start()

        if self._bot_entity is None:
            try:
                self._bot_entity = await get_cached_entity(self.client, settings.bot_username)
            except Exception as exc:
                logger.error("Cannot resolve bot entity: %s", exc)
                return []
        bot = self._bot_entity

        # Send command and wait for response
        response_text = None
        response_event = asyncio.Event()

        @self.client.on(events.NewMessage(from_users=bot))
        async def _handler(event: events.NewMessage.Event):
            nonlocal response_text
            response_text = event.raw_text
            response_event.set()

        try:
            await self.client.send_message(bot, "/leaderboard")
            try:
                await asyncio.wait_for(response_event.wait(), timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Bot did not respond to /leaderboard in time")
                return []
        finally:
            self.client.remove_event_handler(_handler)

        if not response_text:
            return []

        entries = self._parse_leaderboard_text(response_text)

        # Download avatars for each entry
        for entry in entries:
            entry["avatar_b64"] = await self._get_avatar(entry["username"])

        return entries

    def preload_avatar_cache(self, avatar_map: dict) -> None:
        """
        Pre-populate the in-memory avatar cache from DB data.
        Call once on startup so restart doesn't re-download all avatars.
        avatar_map: {username: base64_str}  (None values are skipped)
        """
        loaded = 0
        for username, b64 in avatar_map.items():
            if b64 and username and username not in self._avatar_cache:
                self._avatar_cache[username] = b64
                loaded += 1
        if loaded:
            logger.info("Avatar cache pre-loaded: %d entries from DB", loaded)

    async def _get_avatar(self, username: str) -> str | None:
        """Download Telegram profile photo and return as base64 string."""
        # Use cache to avoid re-downloading every update
        if username in self._avatar_cache:
            return self._avatar_cache[username]
        try:
            entity = await get_cached_entity(self.client, username)
            buf = io.BytesIO()
            result = await self.client.download_profile_photo(entity, file=buf, download_big=False)
            if result:
                b64 = base64.b64encode(buf.getvalue()).decode()
                self._avatar_cache[username] = b64
                return b64
        except Exception as exc:
            logger.debug("No avatar for %s: %s", username, exc)
        return None

    # ------------------------------------------------------------------
    # Parsing helpers — adjust patterns to match bot's actual format
    # ------------------------------------------------------------------

    def _parse_ref_leaderboard_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse ref leaderboard format:
        '1. Display Name (https://t.me/username) — 128741 pts'
        or just '1. Display Name — 128741 pts' (when URL is a message entity)
        Medal emojis are normalized first.
        """
        text = text.replace("🥇", "1.").replace("🥈", "2.").replace("🥉", "3.")

        entries: List[Dict[str, Any]] = []

        # Pattern with t.me URL in text: "1. Display Name (https://t.me/username) — score"
        pattern_with_url = re.compile(
            r"(\d+)[.)]\s+(.+?)\s*\(https?://t\.me/([^)]+)\)\s*[-—–]+\s*([\d,]+)",
            re.MULTILINE,
        )
        matches = pattern_with_url.findall(text)
        for rank_str, display_name, username, score_str in matches:
            try:
                entries.append({
                    "rank": int(rank_str),
                    "username": username.strip().lstrip("@"),
                    "display_name": display_name.strip(),
                    "score": int(score_str.replace(",", "")),
                    "avatar_b64": None,
                    "extra_data": {"raw": text[:200]},
                })
            except ValueError:
                continue

        if entries:
            return entries

        # Fallback: "1. Display Name — score" (URL as entity, not in raw text)
        # Handles both single-word @username and multi-word display names
        pattern_multiword = re.compile(
            r"(\d+)[.)]\s+(.+?)\s*[-—–]+\s*([\d,]+)(?:\s*pts?)?$",
            re.MULTILINE,
        )
        matches = pattern_multiword.findall(text)
        for rank_str, display_name, score_str in matches:
            display_name = display_name.strip().rstrip("(")
            username = display_name.lstrip("@").split()[0] if display_name else "unknown"
            try:
                entries.append({
                    "rank": int(rank_str),
                    "username": username.strip().lstrip("@"),
                    "display_name": display_name,
                    "score": int(score_str.replace(",", "")),
                    "avatar_b64": None,
                    "extra_data": {"raw": text[:200]},
                })
            except ValueError:
                continue

        if not entries:
            logger.warning("Could not parse ref leaderboard text:\n%s", text)

        return entries

    def _parse_leaderboard_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse leaderboard text from bot response.
        Tries multiple patterns to be resilient to different bot formats.
        """
        # Normalize medal emojis → numeric ranks so existing patterns match top-3
        text = text.replace("🥇", "1.").replace("🥈", "2.").replace("🥉", "3.")

        entries: List[Dict[str, Any]] = []

        # Pattern 1: "1. @username — 1234 pts"  or  "1. username - 1234"
        pattern_v1 = re.compile(
            r"(\d+)[.)]\s*@?(\S+)\s*[-—–]+\s*([\d,]+(?:\.\d+)?)",
            re.MULTILINE,
        )
        # Pattern 2: "#1  username  1234"
        pattern_v2 = re.compile(
            r"#?(\d+)\s+@?(\S+)\s+([\d,]+(?:\.\d+)?)",
            re.MULTILINE,
        )
        # Pattern 3: "1 | username | 1234"
        pattern_v3 = re.compile(
            r"(\d+)\s*\|\s*@?(\S+)\s*\|\s*([\d,]+(?:\.\d+)?)",
            re.MULTILINE,
        )

        for pattern in (pattern_v1, pattern_v2, pattern_v3):
            matches = pattern.findall(text)
            if matches:
                for match in matches:
                    rank_str, username, score_str = match
                    score_clean = score_str.replace(",", "")
                    try:
                        entries.append(
                            {
                                "rank": int(rank_str),
                                "username": username.strip("@. "),
                                "display_name": username.strip("@. "),
                                "score": int(float(score_clean)),
                                "avatar_b64": None,
                                "extra_data": {"raw": text[:200]},
                            }
                        )
                    except ValueError:
                        continue
                break  # use first successful pattern

        if not entries:
            logger.warning("Could not parse leaderboard text:\n%s", text)

        return entries


# Singleton
telegram_parser = TelegramParser()
