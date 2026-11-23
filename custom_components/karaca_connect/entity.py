"""Base entity for Karaca Connect."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KaracaCoordinator, KaracaDevice


class KaracaEntity(CoordinatorEntity[KaracaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: KaracaCoordinator, device_id: int, key: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        dev = self.device
        self._attr_unique_id = f"{dev.info.get('udid') or dev.id}_{key}"
        product = dev.info.get("product") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(dev.id))},
            name=dev.name,
            manufacturer="Karaca",
            model=product.get("name") or dev.info.get("modelNumber"),
            model_id=dev.info.get("modelNumber"),
            serial_number=dev.info.get("serialNumber"),
        )

    @property
    def device(self) -> KaracaDevice:
        return self.coordinator.data[self._device_id]

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data
