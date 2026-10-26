"""Config flow for LiveKid: paste the Bearer token from the web app."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig
from homeassistant.util import dt as dt_util

from .api import (
    LiveKidApi,
    LiveKidAuthError,
    LiveKidConnectionError,
    LiveKidError,
    extract_token,
)
from .const import CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(multiline=True))}
)


class LiveKidConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, raw: str) -> tuple[str | None, LiveKidApi | None, dict[str, Any] | None, str | None]:
        """Return (token, api, balance_row, error_key)."""
        token = extract_token(raw)
        if not token:
            return None, None, None, "no_token"
        try:
            api = LiveKidApi(async_get_clientsession(self.hass), token)
            if "kid" not in api.claims:
                return None, None, None, "no_kid"
            now = dt_util.now()
            await api.get_presence_minutes(now.year, now.month)
            balance = await api.get_balance()
        except LiveKidAuthError:
            return None, None, None, "invalid_auth"
        except LiveKidConnectionError:
            return None, None, None, "cannot_connect"
        except LiveKidError:
            _LOGGER.exception("Unexpected LiveKid error")
            return None, None, None, "unknown"
        # An expired paste was refreshed during validation; keep the working token.
        return api.token, api, balance, None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token, api, balance, error = await self._validate(user_input[CONF_TOKEN])
            if error:
                errors["base"] = error
            else:
                assert api is not None
                await self.async_set_unique_id(f"{api.claims.get('id')}_{api.kid_id}")
                self._abort_if_unique_id_configured()
                name = (balance or {}).get("name") or f"#{api.kid_id}"
                return self.async_create_entry(title=f"LiveKid ({name})", data={CONF_TOKEN: token})
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token, api, _, error = await self._validate(user_input[CONF_TOKEN])
            if error:
                errors["base"] = error
            else:
                assert api is not None
                await self.async_set_unique_id(f"{api.claims.get('id')}_{api.kid_id}")
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_TOKEN: token}
                )
        return self.async_show_form(step_id="reauth_confirm", data_schema=SCHEMA, errors=errors)
