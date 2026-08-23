"""Battery lifetime tracking manager."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


from .const import (
    CHECK_INTERVAL,
    DOMAIN,
    REASON_BATTERY_EMPTY,
    REASON_DEVICE_UNAVAILABLE,
    STORAGE_KEY,
    STORAGE_VERSION,
)


class BatteryLifetimeManager:
    """Discover battery sensors, track cycles, and persist history."""

    def __init__(self, hass: HomeAssistant, unavailable_hours: int) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.unavailable_timeout = timedelta(hours=unavailable_hours)
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            private=True,
            atomic_writes=True,
        )
        self._data: dict[str, Any] = {"sources": {}}
        self._source_listeners: dict[str, CALLBACK_TYPE] = {}
        self._unsub_new_sensor: CALLBACK_TYPE | None = None
        self._unsub_interval: CALLBACK_TYPE | None = None

    @property
    def source_ids(self) -> list[str]:
        """Return all known source IDs."""
        return list(self._data["sources"])

    async def async_load(self) -> None:
        """Load persisted tracking data."""
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("sources"), dict):
            self._data = stored

    @callback
    def async_discover_existing(self) -> None:
        """Discover all current battery sensor states."""
        for state in self.hass.states.async_all("sensor"):
            if self._is_battery_sensor(state):
                self._async_register_source(state)


    async def async_backfill_active_starts(self) -> None:
        """Backfill missing active starts from Recorder history when available."""
        if "recorder" not in self.hass.config.components:
            _LOGGER.debug("Recorder is not loaded; skipping battery history backfill")
            return

        source_ids: list[str] = []
        entity_ids: list[str] = []
        for source_id in self.source_ids:
            record = self.get_record(source_id)
            if record.get("active_start") is not None:
                continue
            entity_id = record.get("entity_id")
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            value = self._battery_value(state)
            if value is None or value <= 0.0:
                continue
            source_ids.append(source_id)
            entity_ids.append(entity_id)

        if not entity_ids:
            return

        try:
            from homeassistant.components.recorder import get_instance, history

            instance = get_instance(self.hass)
            # Query farther back than normal Recorder retention. Recorder itself limits
            # the result to data that still exists in the database. Battery sensors
            # generally have relatively few state changes, so one batched query keeps
            # startup load modest even with many battery entities.
            start_time = dt_util.utcnow() - timedelta(days=3650)
            history_by_entity = await instance.async_add_executor_job(
                history.get_significant_states,
                self.hass,
                start_time,
                None,
                entity_ids,
                None,
                True,
                False,
                False,
                True,
                False,
            )
        except Exception:  # Recorder may be unavailable or still starting.
            _LOGGER.exception("Unable to read Recorder history for battery backfill")
            return

        changed = False
        now = dt_util.utcnow()
        source_by_entity = dict(zip(entity_ids, source_ids, strict=True))

        for entity_id, source_id in source_by_entity.items():
            states = history_by_entity.get(entity_id, [])
            backfilled = self._find_active_start_from_history(states, now)
            if backfilled is None:
                continue

            record = self.get_record(source_id)
            # A live state event may have started a cycle while the history query was
            # running. Never overwrite a start already learned by live tracking.
            if record.get("active_start") is None:
                record["active_start"] = backfilled.isoformat()
                changed = True

        if changed:
            await self._store.async_save(self._data)

    def _find_active_start_from_history(
        self, states: list[State | dict[str, Any]], now: datetime
    ) -> datetime | None:
        """Find the current cycle's start from a chronological history list."""
        candidate: datetime | None = None
        unavailable_since: datetime | None = None
        previous_was_full = False

        for item in states:
            if not isinstance(item, State):
                continue

            when = item.last_updated
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt_util.UTC)

            if item.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                if unavailable_since is None:
                    unavailable_since = when
                previous_was_full = False
                continue

            if unavailable_since is not None:
                if when - unavailable_since >= self.unavailable_timeout:
                    candidate = None
                unavailable_since = None

            value = self._battery_value(item)
            if value is None:
                previous_was_full = False
                continue

            if value <= 0.0:
                candidate = None
                previous_was_full = False
                continue

            is_full = value >= 100.0
            if is_full and not previous_was_full:
                candidate = when
            previous_was_full = is_full

        if unavailable_since is not None and now - unavailable_since >= self.unavailable_timeout:
            return None
        return candidate

    async def async_start(self) -> None:
        """Start listeners and reconcile current states."""
        for source_id in list(self.source_ids):
            record = self.get_record(source_id)
            entity_id = record.get("entity_id")
            if entity_id:
                self._async_attach_source_listener(source_id, entity_id)

        self._unsub_new_sensor = async_track_state_added_domain(
            self.hass, "sensor", self._async_new_sensor_state
        )
        self._unsub_interval = async_track_time_interval(
            self.hass, self._async_periodic_check, CHECK_INTERVAL
        )

        for source_id in list(self.source_ids):
            entity_id = self.get_record(source_id).get("entity_id")
            if entity_id and (state := self.hass.states.get(entity_id)) is not None:
                await self._async_process_state(source_id, state)

        await self._async_check_unavailable_timeouts(dt_util.utcnow())

    async def async_stop(self) -> None:
        """Stop listeners and flush storage."""
        if self._unsub_new_sensor:
            self._unsub_new_sensor()
            self._unsub_new_sensor = None
        if self._unsub_interval:
            self._unsub_interval()
            self._unsub_interval = None
        for unsub in self._source_listeners.values():
            unsub()
        self._source_listeners.clear()
        await self._store.async_save(self._data)

    def get_record(self, source_id: str) -> dict[str, Any]:
        """Return the stored record for one source."""
        return self._data["sources"][source_id]

    def is_ignored(self, source_id: str) -> bool:
        """Return whether a source is ignored."""
        return bool(self.get_record(source_id).get("ignored", False))

    async def async_set_ignored(self, source_id: str, ignored: bool) -> None:
        """Ignore or restore one battery source."""
        if source_id not in self._data["sources"]:
            raise KeyError(source_id)

        record = self.get_record(source_id)
        if bool(record.get("ignored", False)) == ignored:
            return

        # Ignoring affects only visibility in the UI. Tracking continues in the
        # background exactly as for non-ignored battery sources.
        record["ignored"] = ignored
        await self._store.async_save(self._data)

    def source_name(self, source_id: str) -> str:
        """Return a friendly name for a source."""
        record = self.get_record(source_id)
        entity_id = record.get("entity_id")
        if entity_id and (state := self.hass.states.get(entity_id)) is not None:
            return state.name
        return record.get("name") or entity_id or source_id

    def active_start(self, source_id: str) -> datetime | None:
        """Return active cycle start."""
        return self._parse_datetime(self.get_record(source_id).get("active_start"))

    def current_duration_seconds(self, source_id: str) -> float | None:
        """Return current active-cycle duration."""
        start = self.active_start(source_id)
        if start is None:
            return None
        return max(0.0, (dt_util.utcnow() - start).total_seconds())

    def completed_cycles(self, source_id: str) -> list[dict[str, Any]]:
        """Return completed cycles."""
        return list(self.get_record(source_id).get("cycles", []))

    def duration_values(self, source_id: str) -> list[float]:
        """Return completed cycle durations."""
        return [
            float(cycle["duration_seconds"])
            for cycle in self.completed_cycles(source_id)
            if isinstance(cycle.get("duration_seconds"), (int, float))
        ]

    def expected_empty(self, source_id: str) -> datetime | None:
        """Return expected empty time from completed-cycle average."""
        start = self.active_start(source_id)
        values = self.duration_values(source_id)
        if start is None or not values:
            return None
        return start + timedelta(seconds=sum(values) / len(values))

    def export_rows(self) -> list[dict[str, Any]]:
        """Return current tracking data for the UI."""
        rows: list[dict[str, Any]] = []
        now = dt_util.utcnow()

        for source_id in self.source_ids:
            record = self.get_record(source_id)
            entity_id = record.get("entity_id")
            state = self.hass.states.get(entity_id) if entity_id else None
            cycles = self.completed_cycles(source_id)
            values = self.duration_values(source_id)
            last = cycles[-1] if cycles else None
            start = self.active_start(source_id)
            expected = self.expected_empty(source_id)

            battery_level: float | None = None
            state_text = None
            if state is not None:
                state_text = state.state
                battery_level = self._battery_value(state)

            rows.append(
                {
                    "source_id": source_id,
                    "entity_id": entity_id,
                    "name": self.source_name(source_id),
                    "battery_level": battery_level,
                    "state": state_text,
                    "ignored": self.is_ignored(source_id),
                    "active": start is not None,
                    "cycle_started": start.isoformat() if start else None,
                    "current_duration_seconds": (
                        max(0.0, (now - start).total_seconds()) if start else None
                    ),
                    "unavailable_since": record.get("unavailable_since"),
                    "completed_cycles": len(cycles),
                    "last_duration_seconds": (
                        last.get("duration_seconds") if last else None
                    ),
                    "last_start": last.get("start") if last else None,
                    "last_end": last.get("end") if last else None,
                    "last_end_reason": last.get("reason") if last else None,
                    "average_duration_seconds": (
                        sum(values) / len(values) if values else None
                    ),
                    "shortest_duration_seconds": min(values) if values else None,
                    "longest_duration_seconds": max(values) if values else None,
                    "expected_empty": expected.isoformat() if expected else None,
                }
            )

        rows.sort(key=lambda row: str(row.get("name") or "").casefold())
        return rows

    @callback
    def _async_new_sensor_state(self, event: Event[EventStateChangedData]) -> None:
        """Handle a newly added sensor state."""
        new_state = event.data.get("new_state")
        if new_state is None or not self._is_battery_sensor(new_state):
            return
        source_id = self._async_register_source(new_state)
        self.hass.async_create_task(self._async_process_state(source_id, new_state))

    @callback
    def _async_register_source(self, state: State) -> str:
        """Register a battery sensor and attach its listener."""
        source_id = self._source_id_for_entity(state.entity_id)
        is_new = source_id not in self._data["sources"]

        if is_new:
            self._data["sources"][source_id] = {
                "entity_id": state.entity_id,
                "name": state.name,
                "active_start": None,
                "unavailable_since": None,
                "cycles": [],
                "ignored": False,
            }
        else:
            record = self.get_record(source_id)
            record["entity_id"] = state.entity_id
            record["name"] = state.name

        self._async_attach_source_listener(source_id, state.entity_id)

        if is_new:
            self._schedule_save()
        return source_id

    @callback
    def _async_attach_source_listener(self, source_id: str, entity_id: str) -> None:
        """Attach or replace the state listener for a tracked source."""
        if source_id in self._source_listeners:
            self._source_listeners[source_id]()

        @callback
        def _state_changed(event: Event[EventStateChangedData]) -> None:
            new_state = event.data.get("new_state")
            if new_state is None:
                self.hass.async_create_task(self._async_mark_unavailable(source_id))
                return
            self.hass.async_create_task(self._async_process_state(source_id, new_state))

        self._source_listeners[source_id] = async_track_state_change_event(
            self.hass, entity_id, _state_changed
        )

    async def _async_mark_unavailable(self, source_id: str) -> None:
        """Mark a tracked entity unavailable when its state disappears."""
        record = self.get_record(source_id)
        if record.get("active_start") and not record.get("unavailable_since"):
            record["unavailable_since"] = dt_util.utcnow().isoformat()
            self._schedule_save()

    async def _async_process_state(self, source_id: str, state: State) -> None:
        """Process a source battery state change."""
        record = self.get_record(source_id)

        changed = False
        now = dt_util.utcnow()

        if state.entity_id != record.get("entity_id"):
            record["entity_id"] = state.entity_id
            changed = True
        if state.name != record.get("name"):
            record["name"] = state.name
            changed = True

        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            if record.get("active_start") and not record.get("unavailable_since"):
                record["unavailable_since"] = now.isoformat()
                changed = True
        else:
            if record.get("unavailable_since") is not None:
                record["unavailable_since"] = None
                changed = True

            value = self._battery_value(state)
            if value is not None:
                if value >= 100.0 and record.get("active_start") is None:
                    record["active_start"] = now.isoformat()
                    changed = True
                elif value <= 0.0 and record.get("active_start") is not None:
                    self._complete_cycle(source_id, end=now, reason=REASON_BATTERY_EMPTY)
                    changed = True

        if changed:
            self._schedule_save()

    async def _async_periodic_check(self, now: datetime) -> None:
        """Detect long unavailability."""
        await self._async_check_unavailable_timeouts(now)

    async def _async_check_unavailable_timeouts(self, now: datetime) -> None:
        """Complete cycles whose source stayed unavailable long enough."""
        changed = False
        for source_id in list(self.source_ids):
            record = self.get_record(source_id)
            if record.get("active_start") is None:
                continue
            unavailable_since = self._parse_datetime(record.get("unavailable_since"))
            if unavailable_since is None:
                continue
            if now - unavailable_since >= self.unavailable_timeout:
                self._complete_cycle(
                    source_id,
                    end=unavailable_since,
                    reason=REASON_DEVICE_UNAVAILABLE,
                )
                changed = True

        if changed:
            self._schedule_save()

    @callback
    def _complete_cycle(self, source_id: str, end: datetime, reason: str) -> None:
        """Complete and store one battery cycle."""
        record = self.get_record(source_id)
        start = self._parse_datetime(record.get("active_start"))
        if start is None:
            return
        duration = max(0.0, (end - start).total_seconds())
        record.setdefault("cycles", []).append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_seconds": duration,
                "reason": reason,
            }
        )
        record["active_start"] = None
        record["unavailable_since"] = None

    @callback
    def _schedule_save(self) -> None:
        """Debounce persistent storage writes."""
        self._store.async_delay_save(lambda: self._data, 2)

    @callback
    def _source_id_for_entity(self, entity_id: str) -> str:
        """Return a stable source ID where possible."""
        registry = er.async_get(self.hass)
        if entry := registry.async_get(entity_id):
            return f"registry:{entry.id}"
        return f"entity:{entity_id}"

    @staticmethod
    def _battery_value(state: State) -> float | None:
        """Return battery percentage when valid."""
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if 0.0 <= value <= 100.0:
            return value
        return None

    @classmethod
    def _is_battery_sensor(cls, state: State) -> bool:
        """Return True for battery percentage sensors."""
        if state.domain != "sensor":
            return False
        if state.attributes.get(ATTR_DEVICE_CLASS) != "battery":
            return False
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return True
        return cls._battery_value(state) is not None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Parse stored ISO timestamp."""
        if not isinstance(value, str):
            return None
        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return parsed
