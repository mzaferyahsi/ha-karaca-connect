"""AeroFritas air fryer command buttons (stop / pause / continue)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import KaracaError
from .coordinator import KaracaConfigEntry
from .entity import KaracaEntity

COMMANDS = ("stop", "pause", "continue")


async def async_setup_entry(
    hass: HomeAssistant, entry: KaracaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        AirFryerButton(coordinator, dev.id, cmd)
        for dev in coordinator.data.values()
        if dev.kind == "airfryer"
        for cmd in COMMANDS
    )


class AirFryerButton(KaracaEntity, ButtonEntity):
    def __init__(self, coordinator, device_id: int, command: str) -> None:
        super().__init__(coordinator, device_id, f"cmd_{command}")
        self._command = command
        self._attr_translation_key = command

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.airfryer_command(self.device.id, self._command)
        except KaracaError as err:
            raise HomeAssistantError(f"Air fryer {self._command} failed: {err}") from err
        await self.coordinator.async_request_refresh()
