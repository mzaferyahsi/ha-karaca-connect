"""Karaca Connect integration (Robotea tea machines, AeroFritas air fryers)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KaracaApi, KaracaError, Tokens
from .const import (
    ATTR_MODE_ID,
    ATTR_TEMPERATURE,
    ATTR_TIME,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    SERVICE_START_COOKING,
)
from .coordinator import KaracaConfigEntry, KaracaCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

START_COOKING_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required(ATTR_MODE_ID): vol.Coerce(int),
        vol.Required(ATTR_TEMPERATURE): vol.Coerce(int),
        vol.Required(ATTR_TIME): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: KaracaConfigEntry) -> bool:
    language = (hass.config.language or "en").split("-")[0]
    refresh = entry.data.get(CONF_REFRESH_TOKEN)
    api = KaracaApi(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        language=language,
        # An empty access token forces a refresh (then sign-in) on first call.
        tokens=Tokens("", refresh) if refresh else None,
    )
    coordinator = KaracaCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KaracaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START_COOKING):
        return

    async def start_cooking(call: ServiceCall) -> None:
        """Start an AeroFritas program. device_id is the HA device id."""
        device = dr.async_get(hass).async_get(call.data["device_id"])
        if device is None:
            raise ServiceValidationError("Unknown device")
        karaca_id = next((i for d, i in device.identifiers if d == DOMAIN), None)
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
                continue
            coordinator: KaracaCoordinator = entry.runtime_data
            dev = coordinator.data.get(int(karaca_id)) if karaca_id else None
            if dev is None or dev.kind != "airfryer":
                raise ServiceValidationError("Device is not a Karaca air fryer")
            mode_id = call.data[ATTR_MODE_ID]
            # The app sends the mode's name as `label` alongside its id.
            label = next(
                (m.get("name") for m in dev.state.get("modes") or [] if m and m.get("id") == mode_id),
                None,
            )
            try:
                await coordinator.api.airfryer_start(
                    dev.id, mode_id, call.data[ATTR_TEMPERATURE], call.data[ATTR_TIME], label
                )
            except KaracaError as err:
                raise HomeAssistantError(str(err)) from err
            await coordinator.async_request_refresh()
            return
        raise ServiceValidationError("Device does not belong to Karaca Connect")

    hass.services.async_register(DOMAIN, SERVICE_START_COOKING, start_cooking, START_COOKING_SCHEMA)
