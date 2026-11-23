"""Polling coordinator for Karaca Connect."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KaracaApi, KaracaAuthError, KaracaError, device_kind
from .const import CONF_REFRESH_TOKEN, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class KaracaDevice:
    """One device: the list entry plus its latest detail payload."""

    id: int
    kind: str  # "robotea" | "airfryer"
    info: dict[str, Any]
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return (
            self.info.get("label")
            or (self.info.get("product") or {}).get("name")
            or f"Karaca {self.kind} {self.id}"
        )

    @property
    def state(self) -> dict[str, Any]:
        """The inner `detail` object (Robotea or AirFryer)."""
        return self.detail.get("detail") or {}

    @property
    def connected(self) -> bool | None:
        return (self.detail.get("meta") or {}).get("connected")


type KaracaConfigEntry = ConfigEntry[KaracaCoordinator]


class KaracaCoordinator(DataUpdateCoordinator[dict[int, KaracaDevice]]):
    """Fetches the device list and each device's detail."""

    config_entry: KaracaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: KaracaConfigEntry, api: KaracaApi) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL, config_entry=entry
        )
        self.api = api

    async def _async_update_data(self) -> dict[int, KaracaDevice]:
        try:
            devices = await self.api.list_devices()
            result: dict[int, KaracaDevice] = {}
            for info in devices:
                if not info or info.get("id") is None:
                    continue
                dev = KaracaDevice(int(info["id"]), device_kind(info.get("type")), info)
                try:
                    if dev.kind == "robotea":
                        dev.detail = await self.api.get_robotea(dev.id)
                    else:
                        dev.detail = await self.api.get_airfryer(dev.id)
                except KaracaAuthError:
                    raise
                except KaracaError as err:
                    _LOGGER.warning("Could not read %s (%s): %s", dev.name, dev.id, err)
                    if self.data and dev.id in self.data:
                        dev.detail = self.data[dev.id].detail
                result[dev.id] = dev
        except KaracaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KaracaError as err:
            raise UpdateFailed(str(err)) from err

        self._persist_refresh_token()
        return result

    def _persist_refresh_token(self) -> None:
        tokens = self.api.tokens
        if tokens and tokens.refresh_token and (
            self.config_entry.data.get(CONF_REFRESH_TOKEN) != tokens.refresh_token
        ):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_REFRESH_TOKEN: tokens.refresh_token},
            )
