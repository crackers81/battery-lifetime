"""WebSocket API for Battery Lifetime."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, WS_GET_DATA, WS_SET_IGNORED
from .manager import BatteryLifetimeManager


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register Battery Lifetime WebSocket commands."""

    @websocket_api.websocket_command({vol.Required("type"): WS_GET_DATA})
    @websocket_api.async_response
    async def websocket_get_data(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Return all tracked battery information."""
        domain_data = hass.data.get(DOMAIN, {})
        manager: BatteryLifetimeManager | None = domain_data.get("manager")
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Battery Lifetime is not loaded")
            return

        rows = manager.export_rows()
        active_rows = [row for row in rows if not row.get("ignored", False)]
        ignored_rows = [row for row in rows if row.get("ignored", False)]
        connection.send_result(
            msg["id"],
            {
                "count": len(active_rows),
                "ignored_count": len(ignored_rows),
                "batteries": active_rows,
                "ignored_batteries": ignored_rows,
            },
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_SET_IGNORED,
            vol.Required("source_id"): str,
            vol.Required("ignored"): bool,
        }
    )
    @websocket_api.async_response
    async def websocket_set_ignored(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Ignore or restore one battery source."""
        domain_data = hass.data.get(DOMAIN, {})
        manager: BatteryLifetimeManager | None = domain_data.get("manager")
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Battery Lifetime is not loaded")
            return

        try:
            await manager.async_set_ignored(msg["source_id"], msg["ignored"])
        except KeyError:
            connection.send_error(msg["id"], "not_found", "Battery source not found")
            return

        connection.send_result(msg["id"], {"success": True})

    websocket_api.async_register_command(hass, websocket_get_data)
    websocket_api.async_register_command(hass, websocket_set_ignored)
