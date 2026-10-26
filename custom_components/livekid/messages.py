"""Fire Home Assistant events for new staff chat messages and news posts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import LiveKidApi
from .const import DOMAIN, EVENT_MESSAGE, EVENT_NEWS

STORAGE_VERSION = 1


def _when(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, dt_util.get_default_time_zone()).isoformat()


class LiveKidMessages:
    """Tracks the last message seen per chat room and the last news post.

    The first check only records what already exists, so setting the integration up
    does not replay old messages. Messages written by parents are never forwarded.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, api: LiveKidApi) -> None:
        self._hass = hass
        self._api = api
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.seen"
        )
        self._seen: dict[str, Any] | None = None

    async def async_check(self, kid: str) -> None:
        """Fire events for messages and news newer than the stored ones."""
        if self._seen is None:
            self._seen = await self._store.async_load() or {}
        first_run = not self._seen
        seen_chats: dict[str, int] = self._seen.setdefault("chats", {})
        events: list[tuple[str, dict[str, Any]]] = []

        for room in await self._api.get_chats():
            last = (room.get("last_message") or {}).get("id")
            key = str(room["id"])
            if last is None or seen_chats.get(key) == last:
                continue
            if not first_run:
                messages = await self._api.get_chat_messages(room["id"])
                if key in seen_chats:
                    new = [m for m in messages if m["id"] > seen_chats[key]]
                else:  # a room created since the last check
                    new = [m for m in messages if m["date"] > self._seen.get("checked_at", 0)]
                events += [
                    (EVENT_MESSAGE, data)
                    for m in reversed(new)
                    if (data := self._message_data(room, m, kid)) is not None
                ]
            seen_chats[key] = last

        news = [n for n in await self._api.get_news() if not n.get("draft") and not n.get("trashed")]
        if news:
            newest = max(n["id"] for n in news)
            seen_news = self._seen.get("news")
            if not first_run and seen_news is not None:
                new = sorted((n for n in news if n["id"] > seen_news), key=lambda n: n["created_at"])
                events += [(EVENT_NEWS, self._news_data(n, kid)) for n in new]
            self._seen["news"] = max(newest, seen_news or 0)

        self._seen["checked_at"] = int(dt_util.utcnow().timestamp() * 1000)
        await self._store.async_save(self._seen)
        for event_type, data in events:
            self._hass.bus.async_fire(event_type, data)

    async def async_send_latest(self, kid: str) -> None:
        """Fire the newest staff message and the newest news post again, marked as a test."""
        latest: tuple[dict[str, Any], dict[str, Any]] | None = None
        for room in await self._api.get_chats():
            for m in await self._api.get_chat_messages(room["id"]):
                if self._message_data(room, m, kid) is None:
                    continue
                if latest is None or m["date"] > latest[1]["date"]:
                    latest = (room, m)
                break  # newest first: the first staff message is this room's newest
        if latest:
            self._hass.bus.async_fire(
                EVENT_MESSAGE, {**self._message_data(latest[0], latest[1], kid), "test": True}
            )
        news = [n for n in await self._api.get_news() if not n.get("draft") and not n.get("trashed")]
        if news:
            newest = max(news, key=lambda n: n["created_at"])
            self._hass.bus.async_fire(EVENT_NEWS, {**self._news_data(newest, kid), "test": True})

    @staticmethod
    def _message_data(room: dict[str, Any], m: dict[str, Any], kid: str) -> dict[str, Any] | None:
        members = {member.get("id"): member for member in room.get("members") or []}
        author = members.get(m.get("author")) or {}
        if author.get("type") == "parent":
            return None
        return {
            "kid": kid,
            "id": m["id"],
            "chat": room.get("name"),
            "chat_type": room.get("chat_type"),
            "author": m.get("author_name") or author.get("display"),
            "author_type": author.get("type"),
            "text": m.get("text") or "",
            "attachments": len(m.get("attachments") or []) + (1 if m.get("image") else 0),
            "date": _when(m.get("date")),
            "test": False,
        }

    @staticmethod
    def _news_data(n: dict[str, Any], kid: str) -> dict[str, Any]:
        return {
            "kid": kid,
            "id": n["id"],
            "title": n.get("title") or "",
            "body": n.get("body") or "",
            "author": (n.get("author") or {}).get("display"),
            "photos": len(n.get("photos") or []),
            "pinned": bool(n.get("pinned")),
            "date": _when(n.get("created_at")),
            "test": False,
        }
