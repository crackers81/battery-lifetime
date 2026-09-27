"""Constants for Battery Info."""

DOMAIN = "battery_lifetime"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.data"

PANEL_URL_PATH = "battery-lifetime"
PANEL_TITLE_NB = "Batteri info"
PANEL_TITLE_EN = "Battery Info"
PANEL_ICON = "mdi:battery-medium"
STATIC_URL = "/battery_lifetime/frontend"
WS_GET_DATA = "battery_lifetime/get_data"
WS_SET_IGNORED = "battery_lifetime/set_ignored"
WS_SET_BATTERY_TYPE = "battery_lifetime/set_battery_type"
