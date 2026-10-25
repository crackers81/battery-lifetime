## Battery Info 2.0.3

### Fixed

- Battery sensors that have been deleted from Home Assistant are now removed from the Battery Info list instead of staying as "Unavailable".
- Devices that are only temporarily offline are still shown as before.
- Deleted sensors are cleaned up at startup, and removed immediately when an entity is deleted while Home Assistant is running.
- Creates no new entities, helpers, or devices.

## Battery Info 2.0.0

### Major redesign

- Renamed Battery Lifetime to Battery Info.
- Replaced lifetime tracking with a simple, readable battery overview.
- Shows battery type, remaining percentage, status, and a colour-coded level bar.
- Highlights low and critical batteries.
- Keeps search, sorting, ignored devices, and clickable Home Assistant entity names.
- Keeps automatic Zigbee2MQTT battery-type detection and manual battery-type editing.
- Preserves existing manually entered battery types and ignored-device choices.
- Removes battery cycles, duration statistics, Recorder backfill, and estimated replacement dates.
- Creates no new entities, helpers, or devices.

The technical integration domain remains battery_lifetime so existing HACS installations can update without reinstalling the integration.
