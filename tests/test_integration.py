"""Offline tests for the Karaca Connect integration."""

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from custom_components.karaca_connect.const import CONF_REFRESH_TOKEN, DOMAIN

from .conftest import BASE, SIGNIN, add_cloud


def _calls(m, method, path):
    return m.requests.get((method, URL(f"{BASE}/{path}")), [])


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="a@b.c", data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_success(hass: HomeAssistant, mock_api) -> None:
    mock_api.post(f"{BASE}/api/auth/signin", payload=SIGNIN)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    add_cloud(mock_api)  # for the setup that follows entry creation
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: " A@B.c ", CONF_PASSWORD: "pw"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw", CONF_REFRESH_TOKEN: "rt-1"}
    body = _calls(mock_api, "POST", "api/auth/signin")[0].kwargs["json"]
    assert body == {"email": "a@b.c", "password": "pw"}


async def test_config_flow_invalid_auth(hass: HomeAssistant, mock_api) -> None:
    mock_api.post(f"{BASE}/api/auth/signin", status=401, payload={"message": "bad"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "a@b.c", CONF_PASSWORD: "x"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_entities(hass: HomeAssistant, mock_api) -> None:
    add_cloud(mock_api)
    await _setup(hass)

    assert hass.states.get("sensor.kitchen_robotea_mode").state == "Tea brewing"
    assert hass.states.get("sensor.kitchen_robotea_mode_state").state == "Fresh"
    assert hass.states.get("sensor.kitchen_robotea_status").state == "Çayınız Taze"
    assert hass.states.get("sensor.kitchen_robotea_countdown").state == "34:48"
    assert hass.states.get("sensor.kitchen_robotea_countdown").attributes["remaining_seconds"] == 2088
    assert hass.states.get("sensor.kitchen_robotea_tea_freshness").state == "3"
    assert hass.states.get("switch.kitchen_robotea_power").state == "on"
    assert hass.states.get("switch.kitchen_robotea_tea_brewing").state == "on"
    assert hass.states.get("switch.kitchen_robotea_filter_coffee").state == "off"
    assert hass.states.get("switch.kitchen_robotea_baby_food").state == "off"
    # Null modes / sensors on this model are not created; schedule (99) is never a switch.
    assert hass.states.get("switch.kitchen_robotea_herbal_tea") is None
    assert hass.states.get("switch.kitchen_robotea_kettle") is None
    assert hass.states.get("sensor.kitchen_robotea_kettle_temperature") is None
    assert len(hass.states.async_entity_ids("switch")) == 5
    assert hass.states.get("binary_sensor.kitchen_robotea_connectivity").state == "on"

    assert hass.states.get("sensor.air_fryer_state").state == "Cooking"
    assert hass.states.get("sensor.air_fryer_temperature").state == "180"
    assert hass.states.get("sensor.air_fryer_remaining_time").state == "420"
    assert hass.states.get("binary_sensor.air_fryer_connectivity").state == "off"
    assert hass.states.get("button.air_fryer_pause") is not None
    modes = hass.states.get("sensor.air_fryer_mode").attributes["available_modes"]
    assert modes == [{"id": 5, "name": "Fries", "temperature": 180, "time": "15:00"}]


async def test_robotea_switch_sends_mode(hass: HomeAssistant, mock_api) -> None:
    add_cloud(mock_api)
    mock_api.put(f"{BASE}/api/v1/devices/11/modes/6", payload={"succeeded": True, "data": True})
    await _setup(hass)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.kitchen_robotea_boiling_water"}, blocking=True
    )
    call = _calls(mock_api, "PUT", "api/v1/devices/11/modes/6")[0]
    assert call.kwargs["json"] == {"active": True}
    assert call.kwargs["headers"]["Authorization"] == "Bearer jwt-1"


async def test_airfryer_button_and_service(hass: HomeAssistant, mock_api) -> None:
    add_cloud(mock_api)
    mock_api.post(f"{BASE}/api/v1/airfryer/cmd/pause", payload={"succeeded": True})
    mock_api.post(f"{BASE}/api/v1/airfryer/cmd/start", payload={"succeeded": True})
    await _setup(hass)

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.air_fryer_pause"}, blocking=True
    )
    assert _calls(mock_api, "POST", "api/v1/airfryer/cmd/pause")[0].kwargs["json"] == {"deviceId": 22}

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "22")})
    await hass.services.async_call(
        DOMAIN, "start_cooking",
        {"device_id": device.id, "mode_id": 5, "temperature": 190, "time": "12:00"},
        blocking=True,
    )
    assert _calls(mock_api, "POST", "api/v1/airfryer/cmd/start")[0].kwargs["json"] == {
        "deviceId": 22, "mode": {"id": 5, "temp": 190, "time": "12:00", "label": "Fries"}
    }


async def test_401_triggers_refresh(hass: HomeAssistant, mock_api) -> None:
    """A 401 on a data call refreshes the token and retries, like the app's authenticator."""
    mock_api.post(f"{BASE}/api/auth/signin", payload=SIGNIN)
    mock_api.get(f"{BASE}/api/v1/devices/me", status=401)
    mock_api.post(
        f"{BASE}/api/auth/refresh-token",
        payload={"succeeded": True, "data": {"jwToken": "jwt-2", "refreshToken": "rt-2"}},
    )
    add_cloud(mock_api)
    entry = await _setup(hass)
    assert hass.states.get("sensor.kitchen_robotea_mode").state == "Tea brewing"
    refresh = _calls(mock_api, "POST", "api/auth/refresh-token")[0]
    assert refresh.kwargs["json"] == {"refreshToken": "rt-1"}
    assert entry.data[CONF_REFRESH_TOKEN] == "rt-2"


async def test_restart_uses_saved_refresh_token(hass: HomeAssistant, mock_api) -> None:
    """After a restart the stored refresh token is used before falling back to sign-in."""
    mock_api.post(
        f"{BASE}/api/auth/refresh-token",
        payload={"succeeded": True, "data": {"jwToken": "jwt-9", "refreshToken": "rt-9"}},
    )
    add_cloud(mock_api)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="a@b.c",
        data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw", CONF_REFRESH_TOKEN: "rt-saved"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _calls(mock_api, "POST", "api/auth/refresh-token")[0].kwargs["json"] == {"refreshToken": "rt-saved"}
    assert not _calls(mock_api, "POST", "api/auth/signin")
    devices_call = _calls(mock_api, "GET", "api/v1/devices/me")[0]
    assert devices_call.kwargs["headers"]["Authorization"] == "Bearer jwt-9"
    assert entry.data[CONF_REFRESH_TOKEN] == "rt-9"


async def test_stale_tea_has_zero_countdown(hass: HomeAssistant, mock_api) -> None:
    """Observed live: once tea goes stale the server drops the countdown object."""
    import copy

    from .conftest import ROBOTEA

    stale = copy.deepcopy(ROBOTEA)
    detail = stale["data"]["detail"]
    detail.update(modeState=5, modeStateLabel="brewedstale")
    detail["stepView"] = {"id": "teabrewing_brewedstale", "label": "Çay Bayatladı", "countdown": None}
    add_cloud(mock_api, robotea=stale)
    await _setup(hass)

    assert hass.states.get("sensor.kitchen_robotea_countdown").state == "0:00"
    state = hass.states.get("sensor.kitchen_robotea_mode_state")
    assert state.state == "Stale"
    assert state.attributes["raw"] == "brewedstale"
    assert hass.states.get("sensor.kitchen_robotea_status").state == "Çay Bayatladı"


async def test_turkey_time(hass: HomeAssistant, mock_api) -> None:
    """Karaca sends naive Turkish (UTC+3) times; they must not be read as local time."""
    add_cloud(mock_api)
    await _setup(hass)

    # Fixture end is 2026-11-24T00:40:56 Turkey time -> 2026-11-23T21:40:56 UTC.
    assert hass.states.get("sensor.kitchen_robotea_fresh_until").state == "2026-11-23T21:40:56+00:00"
    attrs = hass.states.get("sensor.kitchen_robotea_countdown").attributes
    assert attrs["start"] == "2026-11-23T23:40:56+03:00"
    assert attrs["end"] == "2026-11-24T00:40:56+03:00"
    assert hass.states.get("sensor.kitchen_robotea_tea_freshness").attributes["end"] == (
        "2026-11-24T00:40:56+03:00"
    )


async def test_countdown_from_turkey_end_time(hass: HomeAssistant, mock_api, freezer) -> None:
    """Without remainingSeconds, the countdown is derived from the Turkey-time end."""
    import copy

    from .conftest import ROBOTEA

    data = copy.deepcopy(ROBOTEA)
    del data["data"]["detail"]["stepView"]["countdown"]["remainingSeconds"]
    freezer.move_to("2026-11-23T21:30:56+00:00")  # 10 minutes before the 21:40:56 UTC end
    add_cloud(mock_api, robotea=data)
    await _setup(hass)

    state = hass.states.get("sensor.kitchen_robotea_countdown")
    assert state.state == "10:00"
    assert state.attributes["remaining_seconds"] == 600
