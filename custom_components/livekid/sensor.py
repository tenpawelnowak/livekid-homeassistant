"""Sensors for LiveKid: presence and billing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_CURRENCY
from .coordinator import LiveKidConfigEntry, LiveKidData
from .entity import LiveKidEntity

PRESENCE_STATES = ["present", "absent", "planned_absence", "day_off", "not_yet"]


def _presence(d: LiveKidData) -> str:
    day = d.day
    month_day = d.month.get(d.today.isoformat(), {})
    if day.get("was_present") or month_day.get("is_present"):
        return "present"
    if day.get("planned_absence") or month_day.get("has_planned_absence"):
        return "planned_absence"
    if day.get("absent") or month_day.get("is_absent"):
        return "absent"
    if month_day.get("is_day_off") or d.today.isoformat() in d.days_off:
        return "day_off"
    return "not_yet"


def _to_datetime(value: Any, today: date) -> datetime | None:
    """LiveKid times come as minutes after midnight (e.g. 720 = 12:00); also accept epoch ms or ISO strings."""
    if value is None or value == "":
        return None
    tz = dt_util.get_default_time_zone()
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            return dt_util.utc_from_timestamp(value / 1000)
        if 0 <= value < 24 * 60:
            return datetime.combine(today, time(int(value) // 60, int(value) % 60), tz)
        return dt_util.utc_from_timestamp(value)
    if isinstance(value, str):
        return dt_util.parse_datetime(value)
    return None


def _money(value: Any) -> float | None:
    """LiveKid amounts are integers in grosze (1/100 PLN)."""
    return None if value is None else round(value / 100, 2)


def _money_map(values: dict[str, Any] | None) -> dict[str, float | None] | None:
    return None if values is None else {k: _money(v) for k, v in values.items()}


def _month_count(d: LiveKidData, flag: str) -> int:
    return sum(1 for v in d.month.values() if v.get(flag))


def _bill_attrs(d: LiveKidData) -> dict[str, Any]:
    b = d.bill or {}
    return {
        "date": b.get("date"),
        "payment_due_date": b.get("payment_due_date"),
        "description": b.get("description"),
        "total": _money(b.get("total")),
        "total_by_category": _money_map(b.get("total_by_category")),
        "total_to_pay_by_category": _money_map(b.get("total_to_pay_by_category")),
        "payments": [
            {
                "name": p.get("name"),
                "amount": _money(p.get("amount")),
                "status": p.get("status"),
                "date": dt_util.utc_from_timestamp(p["date"] / 1000).isoformat() if p.get("date") else None,
            }
            for p in b.get("payments") or []
        ],
    }


@dataclass(frozen=True, kw_only=True)
class LiveKidSensorDescription(SensorEntityDescription):
    value_fn: Callable[[LiveKidData], Any]
    attrs_fn: Callable[[LiveKidData], dict[str, Any]] | None = None


SENSORS: tuple[LiveKidSensorDescription, ...] = (
    LiveKidSensorDescription(
        key="presence_today",
        device_class=SensorDeviceClass.ENUM,
        options=PRESENCE_STATES,
        value_fn=_presence,
        attrs_fn=lambda d: {
            "comment": d.day.get("daily_report_comment"),
            "pickuper": d.day.get("pickuper"),
            "no_meals": d.day.get("no_meals"),
        },
    ),
    LiveKidSensorDescription(
        key="drop_off",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _to_datetime(d.day.get("drop_off"), d.today),
    ),
    LiveKidSensorDescription(
        key="pick_up",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _to_datetime(d.day.get("pick_up"), d.today),
    ),
    LiveKidSensorDescription(
        key="planned_in",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _to_datetime(d.day.get("in"), d.today),
    ),
    LiveKidSensorDescription(
        key="planned_out",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _to_datetime(d.day.get("out"), d.today),
    ),
    LiveKidSensorDescription(
        key="hours_this_month",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: round(d.minutes_this_month / 60, 2),
    ),
    LiveKidSensorDescription(
        key="days_present_this_month",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _month_count(d, "is_present"),
        attrs_fn=lambda d: {
            "absent": _month_count(d, "is_absent"),
            "planned_absence": _month_count(d, "has_planned_absence"),
        },
    ),
    LiveKidSensorDescription(
        key="balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=DEFAULT_CURRENCY,
        value_fn=lambda d: _money((d.balance or {}).get("balance_numeric")),
        attrs_fn=lambda d: {"display": (d.balance or {}).get("balance")},
    ),
    LiveKidSensorDescription(
        key="bill_to_pay",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=DEFAULT_CURRENCY,
        value_fn=lambda d: _money((d.bill or {}).get("total_to_pay")),
        attrs_fn=_bill_attrs,
    ),
    LiveKidSensorDescription(
        key="bill_due_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: dt_util.parse_date((d.bill or {}).get("payment_due_date") or ""),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveKidConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LiveKidSensor(coordinator, desc) for desc in SENSORS)


class LiveKidSensor(LiveKidEntity, SensorEntity):
    entity_description: LiveKidSensorDescription

    def __init__(self, coordinator, description: LiveKidSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
