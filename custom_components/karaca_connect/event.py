"""Activity events: one per Karaca device, fired whenever its reported state changes.

Each change also goes onto the event bus as `karaca_connect_event`, so a single
automation can notify on every Karaca device, including ones added later.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import KaracaConfigEntry, KaracaDevice
from .entity import KaracaEntity
from .labels import humanize, mode_name, mode_state_name

BUS_EVENT = f"{DOMAIN}_event"

# Most specific first: one event per poll, typed by the most important change.
EVENT_TYPES = ["connection", "power", "mode", "status"]


def snapshot(dev: KaracaDevice) -> dict[str, Any]:
    """The user-visible facts whose change should be reported."""
    st = dev.state
    snap: dict[str, Any] = {"connection": dev.connected}
    if dev.kind == "robotea":
        modes = st.get("modes") or {}
        snap["power"] = (modes.get("standBy") or {}).get("active")
        snap["mode"] = mode_name(st.get("modeName"))
        snap["status"] = mode_state_name(st.get("modeStateLabel")) or st.get("modeState")
        snap["status_text"] = (st.get("stepView") or {}).get("label")
    else:
        snap["power"] = None
        snap["mode"] = st.get("modeName")
        snap["status"] = humanize(st.get("state"))
        snap["status_text"] = None
    return snap


def describe(name: str, old: dict[str, Any], new: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Return (event_type, data) for what changed between two snapshots, or None."""
    changes: list[str] = []
    changed_keys: list[str] = []

    if old["connection"] != new["connection"] and new["connection"] is not None:
        changes.append("connected" if new["connection"] else "disconnected")
        changed_keys.append("connection")
    if old["power"] != new["power"] and new["power"] is not None:
        changes.append("turned on" if new["power"] else "turned off")
        changed_keys.append("power")
    if old["mode"] != new["mode"] and new["mode"]:
        changes.append(f"mode: {new['mode']}")
        changed_keys.append("mode")
    if (old["status"], old["status_text"]) != (new["status"], new["status_text"]) and (
        new["status"] or new["status_text"]
    ):
        text = new["status"] or ""
        if new["status_text"] and new["status_text"] != text:
            text = f"{text} ({new['status_text']})" if text else new["status_text"]
        changes.append(text)
        changed_keys.append("status")

    if not changes:
        return None
    event_type = next(t for t in EVENT_TYPES if t in changed_keys)
    message = f"{name}: " + ", ".join(changes)
    data = {
        "message": message,
        "changes": changed_keys,
        "previous": {k: old.get(k) for k in changed_keys},
        "current": {k: new.get(k) for k in changed_keys},
        "status_text": new.get("status_text"),
    }
    return event_type, data


async def async_setup_entry(
    hass: HomeAssistant, entry: KaracaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(KaracaActivity(coordinator, dev.id) for dev in coordinator.data.values())


class KaracaActivity(KaracaEntity, EventEntity):
    _attr_translation_key = "activity"
    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id, "activity")
        self._last: dict[str, Any] | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device_id in self.coordinator.data:
            # Baseline only: no notification for whatever state HA starts up in.
            self._last = snapshot(self.device)

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._device_id in self.coordinator.data:
            dev = self.device
            current = snapshot(dev)
            if self._last is not None and (change := describe(dev.name, self._last, current)):
                event_type, data = change
                self._trigger_event(event_type, data)
                self.hass.bus.async_fire(
                    BUS_EVENT,
                    {
                        "type": event_type,
                        "device_id": self.device_entry.id if self.device_entry else None,
                        "karaca_id": dev.id,
                        "device_name": dev.name,
                        "kind": dev.kind,
                        **data,
                    },
                )
            self._last = current
        super()._handle_coordinator_update()
