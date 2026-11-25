"""Sensors for Karaca Connect."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import KaracaConfigEntry, KaracaDevice
from .entity import KaracaEntity
from .labels import humanize, mode_name, mode_state_name


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, kw_only=True)
class KaracaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KaracaDevice], Any]
    attrs_fn: Callable[[KaracaDevice], dict[str, Any]] | None = None


ROBOTEA_SENSORS = (
    KaracaSensorDescription(
        key="mode",
        translation_key="mode",
        value_fn=lambda d: mode_name(d.state.get("modeName")),
        attrs_fn=lambda d: {
            "raw": d.state.get("modeName"),
            "mode_id": d.state.get("mode"),
            "mode_state": d.state.get("modeState"),
            "updated": _iso(d.state.get("updatedDate")),
        },
    ),
    KaracaSensorDescription(
        # Raw "brewedfresh" -> "Fresh", "brewedstale" -> "Stale".
        key="mode_state",
        translation_key="mode_state",
        value_fn=lambda d: mode_state_name(d.state.get("modeStateLabel")),
        attrs_fn=lambda d: {
            "raw": d.state.get("modeStateLabel"),
            "mode_state_id": d.state.get("modeState"),
        },
    ),
    KaracaSensorDescription(
        # Localized text the app shows, e.g. "Çayınız Taze" ("Your tea is fresh").
        key="status",
        translation_key="status",
        value_fn=lambda d: _step(d).get("label"),
        attrs_fn=lambda d: {"step_id": _step(d).get("id")},
    ),
    KaracaSensorDescription(
        # Shown as "34:48" (minutes:seconds). HA can't render a numeric duration that
        # way, so the state is text and the exact seconds stay in `remaining_seconds`.
        key="countdown",
        translation_key="countdown",
        value_fn=lambda d: _clock(_remaining(d)),
        attrs_fn=lambda d: {
            "remaining_seconds": _remaining(d),
            "label": _countdown(d).get("displayText"),
            "start": _iso(_countdown(d).get("startTime")),
            "end": _iso(_countdown(d).get("endTime")),
        },
    ),
    KaracaSensorDescription(
        key="state",
        translation_key="state",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.state.get("state"),
    ),
    KaracaSensorDescription(
        key="freshness",
        translation_key="freshness",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.state.get("freshness") or {}).get("level"),
        attrs_fn=lambda d: {
            "info": _fresh(d).get("info"),
            "show": _fresh(d).get("show"),
            "start": _iso(_fresh(d).get("start")),
            "end": _iso(_fresh(d).get("end")),
        },
    ),
    KaracaSensorDescription(
        # When the current freshness window ends, shown by HA in your own time zone.
        key="fresh_until",
        translation_key="fresh_until",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _tr_time(_countdown(d).get("endTime") or _fresh(d).get("end")),
    ),
)

# Only created when the device reports a value (null on the Robotea Pro 4in1).
ROBOTEA_OPTIONAL_SENSORS = (
    KaracaSensorDescription(
        key="kettle_temperature",
        translation_key="kettle_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.state.get("kettleTemperatureRead"),
    ),
    KaracaSensorDescription(
        key="kettle_temperature_set",
        translation_key="kettle_temperature_set",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.state.get("kettleTemperatureSet"),
    ),
)


def _step(d: KaracaDevice) -> dict[str, Any]:
    return d.state.get("stepView") or {}


def _countdown(d: KaracaDevice) -> dict[str, Any]:
    return _step(d).get("countdown") or {}


def _fresh(d: KaracaDevice) -> dict[str, Any]:
    return d.state.get("freshness") or {}


# Karaca sends wall-clock times in Turkish time without an offset. Turkey has been
# fixed at UTC+3 with no DST since 2016, so a fixed offset is exact and needs no tz
# database lookup inside the event loop.
TURKEY = timezone(timedelta(hours=3), "TRT")


def _tr_time(value: Any) -> datetime | None:
    """'2026-11-25T13:02:21.836385' (Turkey time) -> aware datetime, whole seconds."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TURKEY)
    return parsed.replace(microsecond=0)


def _iso(value: Any) -> str | None:
    """Attribute form: ISO 8601 with the +03:00 offset, e.g. '2026-11-25T13:02:21+03:00'."""
    parsed = _tr_time(value)
    return parsed.isoformat() if parsed else value


def _remaining(d: KaracaDevice) -> int:
    """Seconds left; 0 when nothing is counting down.

    Uses the server's remainingSeconds (computed in Turkish time on their side). If
    that is missing but an end time is present, derive it from the Turkey-time end.
    """
    cd = _countdown(d)
    seconds = _int(cd.get("remainingSeconds"))
    if seconds is None and (end := _tr_time(cd.get("endTime"))):
        seconds = int((end - dt_util.utcnow()).total_seconds())
    return max(seconds or 0, 0)


def _clock(seconds: int) -> str:
    """2088 -> "34:48"; 4000 -> "1:06:40"; 0 -> "0:00"."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

AIRFRYER_SENSORS = (
    KaracaSensorDescription(
        key="state",
        translation_key="state",
        value_fn=lambda d: humanize(d.state.get("state")),
        attrs_fn=lambda d: {"raw": d.state.get("state")},
    ),
    KaracaSensorDescription(
        key="mode",
        translation_key="mode",
        value_fn=lambda d: d.state.get("modeName"),
        attrs_fn=lambda d: {
            "mode_id": d.state.get("mode"),
            "available_modes": [
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "temperature": (m.get("temperature") or {}).get("value"),
                    "time": (m.get("time") or {}).get("value"),
                }
                for m in (d.state.get("modes") or [])
                if m
            ],
        },
    ),
    KaracaSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.state.get("temperature"),
    ),
    KaracaSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        value_fn=lambda d: _int(d.state.get("remainingTimeInSeconds")),
    ),
    KaracaSensorDescription(
        key="time",
        translation_key="cook_time",
        value_fn=lambda d: d.state.get("time"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: KaracaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[KaracaSensor] = []
    for dev in coordinator.data.values():
        if dev.kind == "robotea":
            descs = list(ROBOTEA_SENSORS) + [
                d for d in ROBOTEA_OPTIONAL_SENSORS if d.value_fn(dev) is not None
            ]
        else:
            descs = list(AIRFRYER_SENSORS)
        entities.extend(KaracaSensor(coordinator, dev.id, d) for d in descs)
    async_add_entities(entities)


class KaracaSensor(KaracaEntity, SensorEntity):
    entity_description: KaracaSensorDescription

    def __init__(self, coordinator, device_id: int, description: KaracaSensorDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.device) if fn else None
