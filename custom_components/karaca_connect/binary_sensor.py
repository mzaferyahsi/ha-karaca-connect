"""Cloud connectivity of each Karaca device (detail.meta.connected)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KaracaConfigEntry
from .entity import KaracaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: KaracaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ConnectedSensor(coordinator, dev.id) for dev in coordinator.data.values())


class ConnectedSensor(KaracaEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id, "connected")

    @property
    def is_on(self) -> bool | None:
        return self.device.connected
