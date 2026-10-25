## Battery Info 2.0.3

### Fixed

- Battery sensors that have been deleted from Home Assistant are now removed from the Battery Info list instead of staying as "Unavailable".
- Devices that are only temporarily offline are still shown as before.
- Deleted sensors are cleaned up at startup, and removed immediately when an entity is deleted while Home Assistant is running.
- Creates no new entities, helpers, or devices.
