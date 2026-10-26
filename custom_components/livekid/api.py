"""Minimal async client for the LiveKid parent API (no Home Assistant imports)."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import Callable
from datetime import date
from typing import Any

import aiohttp

BASE_URL = "https://pl.api.api-livekid-prod.com"
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
TIMEOUT = aiohttp.ClientTimeout(total=30)


class LiveKidError(Exception):
    """Generic API error."""


class LiveKidAuthError(LiveKidError):
    """Token rejected and not refreshable (revoked session, logged out, login too old)."""


class LiveKidConnectionError(LiveKidError):
    """Network problem or 5xx."""


def extract_token(text: str) -> str | None:
    """Pull a JWT out of pasted text (raw token, 'Bearer …', a header dump or the localStorage JSON)."""
    match = JWT_RE.search(text or "")
    return match.group(0) if match else None


def decode_claims(token: str) -> dict[str, Any]:
    """Decode the JWT payload without verifying the signature."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError) as err:
        raise LiveKidAuthError("Malformed token") from err


async def _error_type(resp: aiohttp.ClientResponse) -> str | None:
    """LiveKid error type from a JSON body like {"error": {"type": "JWTExpired", ...}}."""
    try:
        data = await resp.json(content_type=None)
    except (aiohttp.ClientError, ValueError):
        return None
    error = data.get("error") if isinstance(data, dict) else None
    return error.get("type") if isinstance(error, dict) else None


class LiveKidApi:
    """Read-only access to the endpoints used by the parent web dashboard."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        on_token_refresh: Callable[[str], None] | None = None,
    ) -> None:
        self._session = session
        self._token = token
        self._on_token_refresh = on_token_refresh
        self._refresh_lock = asyncio.Lock()
        self.claims = decode_claims(token)

    @property
    def kid_id(self) -> int:
        return int(self.claims["kid"])

    @property
    def token(self) -> str:
        return self._token

    async def _get(
        self, path: str, params: dict[str, Any] | None = None, *, retry: bool = True
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://app.livekid.com",
            "Referer": "https://app.livekid.com/",
        }
        sent_token = self._token
        try:
            async with self._session.get(
                BASE_URL + path, headers=headers, params=params, timeout=TIMEOUT
            ) as resp:
                # A JWT is only accepted for 24 h after it was issued; LiveKid then answers
                # 401 JWTExpired and expects a refresh (the web app does the same).
                if not (retry and resp.status == 401 and await _error_type(resp) == "JWTExpired"):
                    if resp.status in (401, 403):
                        raise LiveKidAuthError(f"{resp.status} on {path}")
                    if resp.status >= 500:
                        raise LiveKidConnectionError(f"{resp.status} on {path}")
                    if resp.status >= 400:
                        raise LiveKidError(f"{resp.status} on {path}")
                    return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise LiveKidConnectionError(str(err)) from err
        await self.refresh_token(sent_token)
        return await self._get(path, params, retry=False)

    async def refresh_token(self, expired: str) -> None:
        """Swap an expired JWT for a new one in the same session (GET /v1/refresh-jwt)."""
        async with self._refresh_lock:
            if self._token != expired:
                return  # a parallel request already refreshed it
            new = await self._get("/v1/refresh-jwt", retry=False)
            token = extract_token(new if isinstance(new, str) else json.dumps(new))
            if not token:
                raise LiveKidAuthError("refresh-jwt returned no token")
            self._token = token
            self.claims = decode_claims(token)
            if self._on_token_refresh:
                self._on_token_refresh(token)

    async def get_presence_day(self, day: date) -> dict[str, Any]:
        """Day detail: was_present, absent, planned_absence, in/out (minutes after midnight), drop_off, pick_up."""
        return await self._get(f"/v1/presence/{day.isoformat()}/{self.kid_id}")

    async def get_presence_month(self, year: int, month: int) -> dict[str, Any]:
        """{'kid', 'rev', 'days': {'YYYY-MM-DD': {is_present, is_absent, has_planned_absence, is_day_off, ...}}}."""
        return await self._get(
            f"/v1/presence/{year:04d}-{month:02d}/{self.kid_id}", {"view": "true"}
        )

    async def get_presence_minutes(self, year: int, month: int) -> int:
        """Total presence time in the month, in minutes."""
        data = await self._get(f"/v1/presence-time/{year:04d}-{month:02d}")
        return int(data.get("time") or 0)

    async def get_days_off(self, year: int) -> list[str]:
        """ISO dates the school is closed (weekends and holidays)."""
        return await self._get(f"/v1/workdays/{year}")

    async def get_balance(self) -> dict[str, Any] | None:
        """{'kid', 'balance_numeric', 'balance', 'name', 'surname', 'display', ...} for this kid."""
        rows = await self._get("/v1/report/balance", {"view": "true"})
        for row in rows or []:
            if row.get("kid") == self.kid_id:
                return row
        return rows[0] if rows else None

    async def get_latest_bill(self) -> dict[str, Any] | None:
        rows = await self._get("/v1/bills", {"limit": 1})
        return rows[0] if rows else None

    async def get_chats(self) -> list[dict[str, Any]]:
        """Chat rooms with 'members' (id, type: parent/teacher/school, display) and 'last_message'."""
        return await self._get("/v1/chats") or []

    async def get_chat_messages(self, chat_id: int) -> list[dict[str, Any]]:
        """Latest 20 messages of a chat room, newest first; 'date' is in milliseconds."""
        return await self._get(f"/v1/chats/{chat_id}/messages") or []

    async def get_news(self) -> list[dict[str, Any]]:
        """News posts (title, body, author.display, photos, created_at in ms); pinned posts come first."""
        return await self._get("/v1/news") or []
