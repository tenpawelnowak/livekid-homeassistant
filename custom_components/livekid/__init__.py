"""LiveKid integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import LiveKidApi
from .const import CONF_TOKEN, DOMAIN
from .coordinator import LiveKidConfigEntry, LiveKidCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def send_latest(call: ServiceCall) -> None:
        """Fire the newest staff message and news post again (test: true), e.g. to test automations."""
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                coordinator: LiveKidCoordinator = entry.runtime_data
                await coordinator.messages.async_send_latest(coordinator.kid_name())

    hass.services.async_register(DOMAIN, "send_latest", send_latest)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LiveKidConfigEntry) -> bool:
    def _store_token(token: str) -> None:
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKEN: token})

    api = LiveKidApi(async_get_clientsession(hass), entry.data[CONF_TOKEN], _store_token)
    coordinator = LiveKidCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LiveKidConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
