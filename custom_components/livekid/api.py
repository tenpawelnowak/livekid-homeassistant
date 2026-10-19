"""Minimal async client for the LiveKid parent API (no Home Assistant imports)."""

from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Any

import aiohttp

BASE_URL = "https://pl.api.api-livekid-prod.com"
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
TIMEOUT = aiohttp.ClientTimeout(total=30)


class LiveKidError(Exception):
    """Generic API error."""


class LiveKidAuthError(LiveKidError):
    """Token rejected (revoked session, logged out)."""


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


class LiveKidApi:
    """Read-only access to the endpoints used by the parent web dashboard."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self.claims = decode_claims(token)

    @property
    def kid_id(self) -> int:
        return int(self.claims["kid"])

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://app.livekid.com",
            "Referer": "https://app.livekid.com/",
        }
        try:
            async with self._session.get(
                BASE_URL + path, headers=headers, params=params, timeout=TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise LiveKidAuthError(f"{resp.status} on {path}")
                if resp.status >= 500:
                    raise LiveKidConnectionError(f"{resp.status} on {path}")
                if resp.status >= 400:
                    raise LiveKidError(f"{resp.status} on {path}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise LiveKidConnectionError(str(err)) from err

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
