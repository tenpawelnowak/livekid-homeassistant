"""Polling coordinator for LiveKid."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LiveKidApi, LiveKidAuthError, LiveKidError
from .const import DOMAIN, SCAN_INTERVAL
from .messages import LiveKidMessages

_LOGGER = logging.getLogger(__name__)

type LiveKidConfigEntry = ConfigEntry[LiveKidCoordinator]


@dataclass
class LiveKidData:
    today: date
    day: dict[str, Any]
    month: dict[str, dict[str, Any]]
    minutes_this_month: int
    days_off: set[str]
    balance: dict[str, Any] | None = None
    bill: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LiveKidCoordinator(DataUpdateCoordinator[LiveKidData]):
    """Fetches today's presence, the month overview, days off and billing for one kid."""

    config_entry: LiveKidConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LiveKidConfigEntry, api: LiveKidApi) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.api = api
        self.messages = LiveKidMessages(hass, entry.entry_id, api)
        self._days_off_cache: dict[int, set[str]] = {}

    async def async_get_days_off(self, year: int) -> set[str]:
        """Days off change rarely; fetch each year once per HA run."""
        if year not in self._days_off_cache:
            self._days_off_cache[year] = set(await self.api.get_days_off(year))
        return self._days_off_cache[year]

    async def _async_update_data(self) -> LiveKidData:
        today = dt_util.now().date()
        try:
            day, month, minutes, days_off = await asyncio.gather(
                self.api.get_presence_day(today),
                self.api.get_presence_month(today.year, today.month),
                self.api.get_presence_minutes(today.year, today.month),
                self.async_get_days_off(today.year),
            )
        except LiveKidAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LiveKidError as err:
            raise UpdateFailed(str(err)) from err

        data = LiveKidData(
            today=today,
            day=day or {},
            month=(month or {}).get("days", {}),
            minutes_this_month=minutes,
            days_off=days_off,
        )

        # Billing is optional: a failure here should not mark presence entities unavailable.
        try:
            data.balance, data.bill = await asyncio.gather(
                self.api.get_balance(), self.api.get_latest_bill()
            )
        except LiveKidAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LiveKidError as err:
            _LOGGER.warning("LiveKid billing update failed: %s", err)
            if self.data:
                data.balance, data.bill = self.data.balance, self.data.bill

        # Messages are optional too: never mark the other entities unavailable because of them.
        try:
            await self.messages.async_check(self.kid_name(data))
        except LiveKidAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LiveKidError as err:
            _LOGGER.warning("LiveKid messages update failed: %s", err)
        return data

    def kid_name(self, data: LiveKidData | None = None) -> str:
        data = data or self.data
        balance = (data.balance if data else None) or {}
        return balance.get("name") or f"#{self.api.kid_id}"
