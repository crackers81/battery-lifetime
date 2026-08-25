"""Battery Lifetime integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_UNAVAILABLE_HOURS,
    DEFAULT_UNAVAILABLE_HOURS,
    DOMAIN,
    PANEL_ICON,
    PANEL_TITLE_EN,
    PANEL_TITLE_NB,
    PANEL_URL_PATH,
    STATIC_URL,
)
from .manager import BatteryLifetimeManager
from .websocket import async_register_websocket

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration-level frontend and WebSocket resources once."""
    hass.data.setdefault(DOMAIN, {})

    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(frontend_dir), False)]
    )
    async_register_websocket(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Battery Lifetime from a config entry."""
    unavailable_hours = int(
        entry.options.get(CONF_UNAVAILABLE_HOURS, DEFAULT_UNAVAILABLE_HOURS)
    )

    manager = BatteryLifetimeManager(hass, unavailable_hours)
    await manager.async_load()
    manager.async_discover_existing()
    await manager.async_backfill_active_starts()
    await manager.async_autofill_battery_types()
    await manager.async_start()

    hass.data.setdefault(DOMAIN, {})["manager"] = manager
    entry.runtime_data = manager

    if PANEL_URL_PATH not in hass.data.get("frontend_panels", {}):
        language = str(getattr(hass.config, "language", "en")).lower()
        panel_title = (
            PANEL_TITLE_NB
            if language.startswith(("nb", "nn", "no"))
            else PANEL_TITLE_EN
        )
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=panel_title,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            config={
                "_panel_custom": {
                    "name": "battery-lifetime-panel",
                    "embed_iframe": False,
                    "trust_external": False,
                    "js_url": f"{STATIC_URL}/battery-lifetime-panel.js",
                }
            },
            require_admin=False,
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Battery Lifetime."""
    manager: BatteryLifetimeManager = entry.runtime_data
    await manager.async_stop()
    hass.data.setdefault(DOMAIN, {}).pop("manager", None)

    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        async_remove_panel(hass, PANEL_URL_PATH)
    return True
