"""Robotea mode switches.

Each entry under detail.modes ({active, mode, name}) becomes a switch; turning it
on or off calls PUT api/v1/devices/{id}/modes/{mode} {active}.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import KaracaError
from .const import ROBOTEA_MODE_KEYS
from .coordinator import KaracaConfigEntry
from .entity import KaracaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: KaracaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for dev in coordinator.data.values():
        if dev.kind != "robotea":
            continue
        modes = dev.state.get("modes") or {}
        for key in ROBOTEA_MODE_KEYS:
            if isinstance(modes.get(key), dict):
                entities.append(RoboteaModeSwitch(coordinator, dev.id, key))
    async_add_entities(entities)


class RoboteaModeSwitch(KaracaEntity, SwitchEntity):
    def __init__(self, coordinator, device_id: int, mode_key: str) -> None:
        super().__init__(coordinator, device_id, f"mode_{mode_key}")
        self._mode_key = mode_key
        self._attr_translation_key = f"mode_{mode_key.lower()}"

    @property
    def _mode(self) -> dict[str, Any]:
        return (self.device.state.get("modes") or {}).get(self._mode_key) or {}

    @property
    def available(self) -> bool:
        return super().available and self._mode.get("mode") is not None

    @property
    def is_on(self) -> bool | None:
        return self._mode.get("active")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mode_id": self._mode.get("mode"), "name": self._mode.get("name")}

    async def _set(self, active: bool) -> None:
        try:
            await self.coordinator.api.set_robotea_mode(
                self.device.id, self._mode["mode"], active
            )
        except KaracaError as err:
            raise HomeAssistantError(f"Could not change {self._mode_key}: {err}") from err
        self._mode["active"] = active
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
