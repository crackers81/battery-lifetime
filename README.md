# Battery Lifetime

[![Validation](https://github.com/crackers81/battery-lifetime/actions/workflows/validate.yml/badge.svg)](https://github.com/crackers81/battery-lifetime/actions/workflows/validate.yml)

Battery Lifetime is a custom Home Assistant integration that tracks battery cycles for existing battery sensor entities and displays the results in a dedicated sidebar panel.

It creates **no new entities, helpers, or devices**.

## Features

- Automatically discovers existing `sensor` entities with `device_class: battery`.
- Starts a battery cycle when the sensor reaches 100%.
- Ends a cycle at 0%, or after the sensor remains `unavailable`/`unknown` for the configured timeout.
- Stores cycle history persistently in Home Assistant `.storage`.
- Backfills a missing active-cycle start from Recorder history when a valid earlier 100% transition exists.
- Shows current duration, previous duration, average duration, completed cycles, and estimated empty date.
- Sorts by battery level, name, or unavailable state.
- Uses mobile cards and a desktop table.
- Supports English and Norwegian Home Assistant installations.
- Opens the existing entity's Home Assistant More Info dialog when its name is clicked.
- Hides ignored batteries from the main view and provides a separate **Ignored** button/view.
- Continues measurement, history handling, and backfill while a battery is ignored.

## Requirements

- Home Assistant with Recorder enabled for historical backfill.
- Existing battery sensors using `device_class: battery`.

Historical backfill can only use Recorder data that Home Assistant still retains. If no suitable 100% state exists, the start date remains unknown until the battery next reaches 100%.

## Installation with HACS

Until this repository is included in the default HACS catalog:

1. Open HACS.
2. Open **Custom repositories**.
3. Add `https://github.com/crackers81/battery-lifetime` as category **Integration**.
4. Install **Battery Lifetime**.
5. Restart Home Assistant.
6. Open **Settings > Devices & services > Add integration** and search for **Battery Lifetime**.

## Manual installation

Copy `custom_components/battery_lifetime` into your Home Assistant configuration directory so the final path is:

```text
/config/custom_components/battery_lifetime
```

Restart Home Assistant, then add **Battery Lifetime** under **Settings > Devices & services**.

## Updating

Update through HACS and restart Home Assistant. You do not need to remove the existing config entry. If the sidebar still shows an older frontend after restart, fully reload the Home Assistant app or browser cache.

## Configuration

During setup, choose how many consecutive hours a battery sensor may remain `unavailable` or `unknown` before its active cycle is ended. The default is 24 hours. This can later be changed under the integration's options.

## Data and privacy

All Battery Lifetime data stays in your Home Assistant instance. The integration does not use cloud services.

## Version 2.4.3

- Ignored batteries are removed from the main view.
- A dedicated button in the upper-right opens the ignored-battery view.
- Ignoring only changes visibility; all measurement continues in the background.
- Battery names remain clickable and open the existing Home Assistant entity dialog.
- Includes English and Norwegian UI support, historical Recorder backfill, and responsive layouts.

## Support

Report problems at https://github.com/crackers81/battery-lifetime/issues.

## License

MIT
