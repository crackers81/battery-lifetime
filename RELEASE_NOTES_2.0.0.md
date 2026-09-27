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
