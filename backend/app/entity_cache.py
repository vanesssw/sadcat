"""
Persistent cache for Telegram entity IDs to avoid ResolveUsernameRequest flood waits.
Saves {name: {id, access_hash, type}} to /app/sessions/entity_cache.json.
"""
import json
import logging
import os

from telethon.tl.types import InputPeerChannel, InputPeerUser, InputPeerChat

logger = logging.getLogger(__name__)

CACHE_FILE = "/app/sessions/entity_cache.json"


def _load() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("Could not save entity cache: %s", e)


def _entity_to_input_peer(entry: dict):
    """Reconstruct InputPeer from cached data (no network call)."""
    t = entry.get("type")
    eid = entry["id"]
    ah = entry.get("access_hash", 0)
    if t == "channel":
        return InputPeerChannel(eid, ah)
    if t == "user":
        return InputPeerUser(eid, ah)
    if t == "chat":
        return InputPeerChat(eid)
    return None


def _entity_type(entity) -> str:
    from telethon.tl.types import Channel, Chat, User
    if isinstance(entity, Channel):
        return "channel"
    if isinstance(entity, Chat):
        return "chat"
    if isinstance(entity, User):
        return "user"
    return "unknown"


async def get_cached_entity(client, name: str):
    """
    Return a Telegram entity for `name`, using disk cache to avoid ResolveUsernameRequest.
    On first call: resolves by username, saves id+access_hash to disk.
    On subsequent calls (even after restart): loads from disk, reconstructs InputPeer.
    """
    data = _load()

    if name in data:
        peer = _entity_to_input_peer(data[name])
        if peer is not None:
            try:
                entity = await client.get_entity(peer)
                return entity
            except Exception as e:
                logger.warning("Cached entity resolve failed for %s: %s — retrying by name", name, e)
                # Fall through to fresh resolve
                del data[name]
                _save(data)

    # Fresh resolve by username
    entity = await client.get_entity(name)

    # Save to disk
    access_hash = getattr(entity, "access_hash", 0)
    data[name] = {
        "id": entity.id,
        "access_hash": access_hash,
        "type": _entity_type(entity),
    }
    _save(data)
    logger.info("Entity cached: %s → id=%s type=%s", name, entity.id, data[name]["type"])
    return entity
