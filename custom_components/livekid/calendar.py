"""Calendar for LiveKid: days off, absences and planned absences."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import LiveKidError
from .coordinator import LiveKidConfigEntry, LiveKidCoordinator
from .entity import LiveKidEntity

MAX_MONTHS = 13


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveKidConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LiveKidCalendar(entry.runtime_data)])


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month) and len(out) < MAX_MONTHS:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _event(day: str, summary: str) -> CalendarEvent:
    start = date.fromisoformat(day)
    return CalendarEvent(start=start, end=start + timedelta(days=1), summary=summary)


class LiveKidCalendar(LiveKidEntity, CalendarEntity):
    def __init__(self, coordinator: LiveKidCoordinator) -> None:
        super().__init__(coordinator, "schedule")

    def _events_from(self, days: dict[str, dict], days_off: set[str]) -> list[CalendarEvent]:
        events = []
        for day, info in sorted(days.items()):
            if info.get("has_planned_absence"):
                events.append(_event(day, "Planowana nieobecność"))
            elif info.get("is_absent"):
                events.append(_event(day, "Nieobecność"))
            elif day in days_off or info.get("is_day_off"):
                # Skip plain weekends; only show holidays/closures on working weekdays.
                if date.fromisoformat(day).weekday() < 5:
                    events.append(_event(day, "Przedszkole zamknięte"))
        return events

    @property
    def event(self) -> CalendarEvent | None:
        data = self.coordinator.data
        today = data.today.isoformat()
        upcoming = [
            e for e in self._events_from(data.month, data.days_off) if e.start.isoformat() >= today
        ]
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start, end = dt_util.as_local(start_date).date(), dt_util.as_local(end_date).date()
        events: list[CalendarEvent] = []
        try:
            for year, month in _months(start, end):
                days_off = await self.coordinator.async_get_days_off(year)
                data = await self.coordinator.api.get_presence_month(year, month)
                events.extend(self._events_from((data or {}).get("days", {}), days_off))
        except LiveKidError:
            return []
        return [e for e in events if start <= e.start < end]
