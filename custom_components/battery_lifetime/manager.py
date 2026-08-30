"""Battery lifetime tracking manager."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import html
import logging
import re
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientTimeout
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

ZIGBEE2MQTT_DEVICE_URL = "https://www.zigbee2mqtt.io/devices/{model}.html"
BATTERY_TYPE_PATTERN = re.compile(
    r"\bUses\s+(?:(?:an?|the)\s+)?(?:(\d+)\s*[x×]\s*)?"
    r"([A-Za-z0-9][A-Za-z0-9+./-]{0,24})\s+batter(?:y|ies)\b",
    re.IGNORECASE,
)


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

    async def async_autofill_battery_types(self) -> None:
        """Fill missing battery types from Zigbee2MQTT device documentation."""
        sources_by_model: dict[str, list[str]] = {}
        for source_id in self.source_ids:
            record = self.get_record(source_id)
            if record.get("battery_type_source") == "manual":
                continue
            if record.get("battery_type"):
                continue
            if model := self._zigbee2mqtt_model(record.get("entity_id")):
                sources_by_model.setdefault(model, []).append(source_id)

        if not sources_by_model:
            return

        semaphore = asyncio.Semaphore(4)

        async def _limited_lookup(model: str) -> tuple[str, str | None]:
            async with semaphore:
                return model, await self._async_lookup_zigbee2mqtt_battery_type(model)

        results = await asyncio.gather(
            *(_limited_lookup(model) for model in sources_by_model)
        )
        changed = False
        for model, battery_type in results:
            if battery_type is None:
                continue
            for source_id in sources_by_model[model]:
                record = self.get_record(source_id)
                if record.get("battery_type_source") == "manual":
                    continue
                record["battery_type"] = battery_type
                record["battery_type_source"] = "zigbee2mqtt"
                record["battery_type_model"] = model
                changed = True

        if changed:
            await self._store.async_save(self._data)

    async def async_autofill_battery_type(self, source_id: str) -> None:
        """Fill one new source's battery type when a reliable match exists."""
        if source_id not in self._data["sources"]:
            return
        record = self.get_record(source_id)
        if record.get("battery_type_source") == "manual" or record.get("battery_type"):
            return
        model = self._zigbee2mqtt_model(record.get("entity_id"))
        if model is None:
            return
        battery_type = await self._async_lookup_zigbee2mqtt_battery_type(model)
        if battery_type is None or record.get("battery_type_source") == "manual":
            return
        record["battery_type"] = battery_type
        record["battery_type_source"] = "zigbee2mqtt"
        record["battery_type_model"] = model
        await self._store.async_save(self._data)

    async def _async_lookup_zigbee2mqtt_battery_type(
        self, model: str
    ) -> str | None:
        """Return a battery type from a Zigbee2MQTT device page."""
        url = ZIGBEE2MQTT_DEVICE_URL.format(model=quote(model, safe=""))
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                timeout=ClientTimeout(total=10),
                headers={"User-Agent": "Home Assistant Battery Lifetime"},
            ) as response:
                if response.status != 200:
                    _LOGGER.debug(
                        "Zigbee2MQTT battery lookup for %s returned HTTP %s",
                        model,
                        response.status,
                    )
                    return None
                body = (await response.content.read(1_000_000)).decode(
                    response.charset or "utf-8", errors="replace"
                )
        except (ClientError, TimeoutError):
            _LOGGER.debug(
                "Unable to look up Zigbee2MQTT battery type for %s",
                model,
                exc_info=True,
            )
            return None

        plain_text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        match = BATTERY_TYPE_PATTERN.search(plain_text)
        if match is None:
            return None
        count, battery_type = match.groups()
        normalized_type = battery_type.upper()
        return f"{count} × {normalized_type}" if count else normalized_type

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

    async def async_set_battery_type(
        self, source_id: str, battery_type: str
    ) -> None:
        """Store a user-defined battery type for one source."""
        if source_id not in self._data["sources"]:
            raise KeyError(source_id)

        normalized = battery_type.strip()[:50]
        record = self.get_record(source_id)
        if str(record.get("battery_type") or "") == normalized:
            return

        record["battery_type"] = normalized or None
        record["battery_type_source"] = "manual"
        record.pop("battery_type_model", None)
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
                    "battery_type": record.get("battery_type"),
                    "battery_type_source": record.get("battery_type_source"),
                    "battery_type_model": record.get("battery_type_model"),
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
        self.hass.async_create_task(self.async_autofill_battery_type(source_id))

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
                "battery_type": None,
                "battery_type_source": None,
                "battery_type_model": None,
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

    @callback
    def _zigbee2mqtt_model(self, entity_id: str | None) -> str | None:
        """Return the model for an entity that belongs to Zigbee2MQTT."""
        if not entity_id:
            return None
        entity_entry = er.async_get(self.hass).async_get(entity_id)
        if entity_entry is None or entity_entry.device_id is None:
            return None
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get(entity_entry.device_id)
        if device is None:
            return None

        markers = [
            str(value)
            for identifier in device.identifiers
            for value in identifier
        ]
        if device.via_device_id and (
            via_device := device_registry.async_get(device.via_device_id)
        ) is not None:
            markers.extend(
                [
                    str(via_device.name or ""),
                    str(via_device.name_by_user or ""),
                    str(via_device.model or ""),
                    *(
                        str(value)
                        for identifier in via_device.identifiers
                        for value in identifier
                    ),
                ]
            )
        if not any("zigbee2mqtt" in marker.casefold() for marker in markers):
            return None

        model = device.model_id or device.model
        return str(model).strip() if model else None

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
