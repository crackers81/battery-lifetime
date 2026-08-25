"""Constants for Battery Lifetime."""

from datetime import timedelta

DOMAIN = "battery_lifetime"

CONF_UNAVAILABLE_HOURS = "unavailable_hours"
DEFAULT_UNAVAILABLE_HOURS = 24
CHECK_INTERVAL = timedelta(minutes=15)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.data"

REASON_BATTERY_EMPTY = "battery_empty"
REASON_DEVICE_UNAVAILABLE = "device_unavailable"

PANEL_URL_PATH = "battery-lifetime"
PANEL_TITLE_NB = "Batterilevetid"
PANEL_TITLE_EN = "Battery Lifetime"
PANEL_ICON = "mdi:battery-clock"
STATIC_URL = "/battery_lifetime/frontend"
WS_GET_DATA = "battery_lifetime/get_data"
WS_SET_IGNORED = "battery_lifetime/set_ignored"
WS_SET_BATTERY_TYPE = "battery_lifetime/set_battery_type"
