"""Config flow for Battery Info."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import DOMAIN


class BatteryInfoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Battery Info config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Battery Info", data={})
        return self.async_show_form(step_id="user")
