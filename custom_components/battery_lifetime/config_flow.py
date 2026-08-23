"""Config flow for Battery Lifetime."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import CONF_UNAVAILABLE_HOURS, DEFAULT_UNAVAILABLE_HOURS, DOMAIN


class BatteryLifetimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Battery Lifetime config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle setup from the UI."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Battery Lifetime",
                data={},
                options={CONF_UNAVAILABLE_HOURS: user_input[CONF_UNAVAILABLE_HOURS]},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UNAVAILABLE_HOURS,
                        default=DEFAULT_UNAVAILABLE_HOURS,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=720))
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return BatteryLifetimeOptionsFlow()


class BatteryLifetimeOptionsFlow(OptionsFlow):
    """Handle Battery Lifetime options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UNAVAILABLE_HOURS,
                        default=self.config_entry.options.get(
                            CONF_UNAVAILABLE_HOURS, DEFAULT_UNAVAILABLE_HOURS
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=720))
                }
            ),
        )
