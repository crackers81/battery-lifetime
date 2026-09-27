"""Battery information manager."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientTimeout
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_added_domain
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)
ZIGBEE2MQTT_DEVICE_URL = "https://www.zigbee2mqtt.io/devices/{model}.html"
BATTERY_TYPE_PATTERN = re.compile(
    r"\bUses\s+(?:(?:an?|the)\s+)?(?:(\d+)\s*[x×]\s*)?"
    r"([A-Za-z0-9][A-Za-z0-9+./-]{0,24})\s+batter(?:y|ies)\b",
    re.IGNORECASE,
)


class BatteryInfoManager:
    """Discover battery sensors and store battery information."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, STORAGE_KEY, private=True, atomic_writes=True
        )
        self._data: dict[str, Any] = {"sources": {}}
        self._unsub_new_sensor: CALLBACK_TYPE | None = None

    @property
    def source_ids(self) -> list[str]:
        return list(self._data["sources"])

    async def async_load(self) -> None:
        """Load settings and remove obsolete lifetime data."""
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("sources"), dict):
            for source_id, old_record in stored["sources"].items():
                if not isinstance(old_record, dict):
                    continue
                self._data["sources"][source_id] = {
                    "entity_id": old_record.get("entity_id"),
                    "name": old_record.get("name"),
                    "ignored": bool(old_record.get("ignored", False)),
                    "battery_type": old_record.get("battery_type"),
                    "battery_type_source": old_record.get("battery_type_source"),
                    "battery_type_model": old_record.get("battery_type_model"),
                }
            await self._store.async_save(self._data)

    @callback
    def async_discover_existing(self) -> None:
        for state in self.hass.states.async_all("sensor"):
            if self._is_battery_sensor(state):
                self._async_register_source(state)

    async def async_start(self) -> None:
        self._unsub_new_sensor = async_track_state_added_domain(
            self.hass, "sensor", self._async_new_sensor_state
        )

    async def async_stop(self) -> None:
        if self._unsub_new_sensor:
            self._unsub_new_sensor()
            self._unsub_new_sensor = None
        await self._store.async_save(self._data)

    def get_record(self, source_id: str) -> dict[str, Any]:
        return self._data["sources"][source_id]

    async def async_set_ignored(self, source_id: str, ignored: bool) -> None:
        if source_id not in self._data["sources"]:
            raise KeyError(source_id)
        self.get_record(source_id)["ignored"] = ignored
        await self._store.async_save(self._data)

    async def async_set_battery_type(self, source_id: str, battery_type: str) -> None:
        if source_id not in self._data["sources"]:
            raise KeyError(source_id)
        record = self.get_record(source_id)
        record["battery_type"] = battery_type.strip()[:50] or None
        record["battery_type_source"] = "manual"
        record.pop("battery_type_model", None)
        await self._store.async_save(self._data)

    async def async_autofill_battery_types(self) -> None:
        sources_by_model: dict[str, list[str]] = {}
        for source_id in self.source_ids:
            record = self.get_record(source_id)
            if record.get("battery_type_source") == "manual" or record.get("battery_type"):
                continue
            if model := self._zigbee2mqtt_model(record.get("entity_id")):
                sources_by_model.setdefault(model, []).append(source_id)

        semaphore = asyncio.Semaphore(4)

        async def lookup(model: str) -> tuple[str, str | None]:
            async with semaphore:
                return model, await self._async_lookup_battery_type(model)

        results = await asyncio.gather(*(lookup(model) for model in sources_by_model))
        changed = False
        for model, battery_type in results:
            if not battery_type:
                continue
            for source_id in sources_by_model[model]:
                record = self.get_record(source_id)
                if record.get("battery_type_source") == "manual":
                    continue
                record.update(
                    battery_type=battery_type,
                    battery_type_source="zigbee2mqtt",
                    battery_type_model=model,
                )
                changed = True
        if changed:
            await self._store.async_save(self._data)

    async def async_autofill_battery_type(self, source_id: str) -> None:
        if source_id not in self._data["sources"]:
            return
        record = self.get_record(source_id)
        if record.get("battery_type_source") == "manual" or record.get("battery_type"):
            return
        model = self._zigbee2mqtt_model(record.get("entity_id"))
        if not model:
            return
        battery_type = await self._async_lookup_battery_type(model)
        if battery_type and record.get("battery_type_source") != "manual":
            record.update(
                battery_type=battery_type,
                battery_type_source="zigbee2mqtt",
                battery_type_model=model,
            )
            await self._store.async_save(self._data)

    async def _async_lookup_battery_type(self, model: str) -> str | None:
        url = ZIGBEE2MQTT_DEVICE_URL.format(model=quote(model, safe=""))
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                timeout=ClientTimeout(total=10),
                headers={"User-Agent": "Home Assistant Battery Info"},
            ) as response:
                if response.status != 200:
                    return None
                body = (await response.content.read(1_000_000)).decode(
                    response.charset or "utf-8", errors="replace"
                )
        except (ClientError, TimeoutError):
            _LOGGER.debug("Unable to look up battery type for %s", model, exc_info=True)
            return None

        plain_text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        match = BATTERY_TYPE_PATTERN.search(plain_text)
        if not match:
            return None
        _, battery_type = match.groups()
        normalized = battery_type.upper()
        return normalized

    def export_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for source_id in self.source_ids:
            record = self.get_record(source_id)
            entity_id = record.get("entity_id")
            state = self.hass.states.get(entity_id) if entity_id else None
            state_text = state.state if state else STATE_UNAVAILABLE
            rows.append(
                {
                    "source_id": source_id,
                    "entity_id": entity_id,
                    "name": state.name if state else record.get("name") or entity_id,
                    "battery_level": self._battery_value(state) if state else None,
                    "state": state_text,
                    "ignored": bool(record.get("ignored", False)),
                    "battery_type": record.get("battery_type"),
                    "battery_type_source": record.get("battery_type_source"),
                    "battery_type_model": record.get("battery_type_model"),
                }
            )
        rows.sort(key=lambda row: str(row.get("name") or "").casefold())
        return rows

    @callback
    def _async_new_sensor_state(self, event: Event[EventStateChangedData]) -> None:
        state = event.data.get("new_state")
        if state is None or not self._is_battery_sensor(state):
            return
        source_id = self._async_register_source(state)
        self.hass.async_create_task(self.async_autofill_battery_type(source_id))

    @callback
    def _async_register_source(self, state: State) -> str:
        source_id = self._source_id_for_entity(state.entity_id)
        record = self._data["sources"].setdefault(
            source_id,
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "ignored": False,
                "battery_type": None,
                "battery_type_source": None,
                "battery_type_model": None,
            },
        )
        record["entity_id"] = state.entity_id
        record["name"] = state.name
        self._store.async_delay_save(lambda: self._data, 2)
        return source_id

    @callback
    def _source_id_for_entity(self, entity_id: str) -> str:
        if entry := er.async_get(self.hass).async_get(entity_id):
            return f"registry:{entry.id}"
        return f"entity:{entity_id}"

    @callback
    def _zigbee2mqtt_model(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        entity = er.async_get(self.hass).async_get(entity_id)
        if entity is None or entity.device_id is None:
            return None
        registry = dr.async_get(self.hass)
        device = registry.async_get(entity.device_id)
        if device is None:
            return None
        markers = [str(value) for _, value in device.identifiers]
        if device.via_device_id and (via := registry.async_get(device.via_device_id)):
            markers.extend(
                [
                    str(via.name or ""), str(via.name_by_user or ""),
                    str(via.model or ""), *(str(value) for _, value in via.identifiers),
                ]
            )
        if not any("zigbee2mqtt" in marker.casefold() for marker in markers):
            return None
        model = device.model_id or device.model
        return str(model).strip() if model else None

    @staticmethod
    def _battery_value(state: State) -> float | None:
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        return value if 0 <= value <= 100 else None

    @classmethod
    def _is_battery_sensor(cls, state: State) -> bool:
        if state.domain != "sensor" or state.attributes.get(ATTR_DEVICE_CLASS) != "battery":
            return False
        return state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) or cls._battery_value(state) is not None
