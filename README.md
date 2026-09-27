# Battery Info

[![Validation](https://github.com/crackers81/battery-lifetime/actions/workflows/validate.yml/badge.svg)](https://github.com/crackers81/battery-lifetime/actions/workflows/validate.yml)

Battery Info is a custom Home Assistant integration that presents battery type and remaining battery level in a simple, readable sidebar overview.

It creates **no new entities, helpers, or devices**.

## Features

- Automatically discovers existing battery sensor entities.
- Shows each device's current battery percentage with a colour-coded progress bar.
- Highlights the number of low batteries in the page summary.
- Stores a manually entered battery type, such as AA, AAA, or CR2032.
- Automatically fills missing battery types for reliably identified Zigbee2MQTT devices when their supported-device page contains a clear battery note.
- Manual battery types are never overwritten by automatic detection.
- Hides battery-type information by default and provides a **Battery** button to show or hide it.
- Supports search and sorting by battery level, availability, or name.
- Opens the existing Home Assistant entity dialog when a device name is clicked.
- Provides a separate view for ignored devices.
- On desktop, devices can be ignored with the **Ignore** button.
- On mobile, tap the percentage or progress bar to ignore a device without using an extra button row.
- Uses a compact responsive layout for desktop and mobile.
- Supports English and Norwegian.

## Installation with HACS

Until this repository is included in the default HACS catalog:

1. Open HACS.
2. Open **Custom repositories**.
3. Add https://github.com/crackers81/battery-lifetime as category **Integration**.
4. Install **Battery Info**.
5. Restart Home Assistant.
6. Open **Settings > Devices & services > Add integration** and search for **Battery Info**.

## Updating from Battery Lifetime

Version 2.0.0 replaces Battery Lifetime with Battery Info. Update through HACS and restart Home Assistant. The existing config entry, manually registered battery types, and ignored-device choices are retained. Lifetime calculations, cycle history, Recorder backfill, and replacement-date estimates are removed.

The technical integration domain remains battery_lifetime so existing HACS installations can update normally.

If the sidebar still shows the previous interface after restarting, fully reload the Home Assistant app or clear the browser cache.

## Manual installation

Copy custom_components/battery_lifetime into your Home Assistant configuration directory at /config/custom_components/battery_lifetime.

Restart Home Assistant and add **Battery Info** under **Settings > Devices & services**.

## Data and privacy

Battery types and ignored-device choices are stored locally in Home Assistant. For confirmed Zigbee2MQTT devices with no saved battery type, the integration can request the matching public device page from zigbee2mqtt.io. Successful results are cached locally.

## Version 2.0.0

- Renamed the integration and sidebar panel to Battery Info.
- Replaced battery-lifetime tracking with a focused battery-information overview.
- Removed cycles, duration statistics, Recorder backfill, and expected replacement dates.
- Added clear colour-coded battery-level progress bars.
- Added a Battery button that shows or hides battery types and editing controls.
- Added compact desktop and mobile layouts.
- On mobile, the percentage and progress bar open the ignore confirmation.
- Retained automatic and manual battery-type registration.
- Preserves existing manual battery types and ignored-device choices during upgrade.
- Creates no new entities, helpers, or devices.

## Support

Report problems at https://github.com/crackers81/battery-lifetime/issues.

## License

MIT
