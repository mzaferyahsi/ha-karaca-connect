"""Activity events / bus events on Karaca state changes."""

import copy

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.karaca_connect.const import DOMAIN

from .conftest import AIRFRYER, BASE, DEVICES, ROBOTEA, SIGNIN


def _robotea(label=None, step=None, power=True, connected=True, mode="teabrewing", remaining=None):
    data = copy.deepcopy(ROBOTEA)
    d = data["data"]["detail"]
    d["modeName"] = mode
    if label:
        d["modeStateLabel"] = label
    if step is not None:
        countdown = None
        if remaining is not None:
            countdown = {"remainingSeconds": remaining, "endTime": "2026-11-24T00:40:56.288136"}
        d["stepView"] = {"id": f"{mode}_{label}", "label": step, "countdown": countdown}
    d["modes"]["standBy"]["active"] = power
    data["data"]["meta"]["connected"] = connected
    return data


async def _setup(hass, mock_api, sequence):
    """sequence: Robotea payloads returned on successive polls (first = startup)."""
    mock_api.post(f"{BASE}/api/auth/signin", payload=SIGNIN, repeat=True)
    mock_api.get(f"{BASE}/api/v1/devices/me", payload=DEVICES, repeat=True)
    mock_api.get(f"{BASE}/api/v1/products/aerofritas/devices/22", payload=AIRFRYER, repeat=True)
    for payload in sequence:
        mock_api.get(f"{BASE}/api/v1/devices/11", payload=payload)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="a@b.c", data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _poll(hass, entry):
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_status_changes_fire_events(hass: HomeAssistant, mock_api) -> None:
    events = async_capture_events(hass, "karaca_connect_event")
    entry = await _setup(
        hass,
        mock_api,
        [
            _robotea("brewing", "Çay Demleniyor"),
            _robotea("brewedfresh", "Çayınız Taze"),
            _robotea("brewedfresh", "Çayınız Taze"),  # unchanged: no event
            _robotea("brewedstale", "Çay Bayatladı"),
        ],
    )
    assert events == []  # startup state is a baseline, not a change

    for _ in range(3):
        await _poll(hass, entry)

    assert [e.data["message"] for e in events] == [
        "Kitchen Robotea: tea is brewed",
        "Kitchen Robotea: tea is no longer fresh",
    ]
    assert events[0].data["type"] == "status"
    assert events[0].data["device_name"] == "Kitchen Robotea"
    assert events[0].data["device_id"]

    state = hass.states.get("event.kitchen_robotea_activity")
    assert state.attributes["event_type"] == "status"
    assert state.attributes["message"] == "Kitchen Robotea: tea is no longer fresh"


async def test_connection_and_power_changes(hass: HomeAssistant, mock_api) -> None:
    events = async_capture_events(hass, "karaca_connect_event")
    entry = await _setup(
        hass,
        mock_api,
        [
            _robotea("brewedfresh", "Çayınız Taze"),
            _robotea("brewedfresh", "Çayınız Taze", connected=False),
            _robotea("off", "Kapalı", power=False, mode="standby"),
        ],
    )
    await _poll(hass, entry)
    await _poll(hass, entry)

    assert events[0].data["type"] == "connection"
    assert events[0].data["message"] == "Kitchen Robotea: disconnected"
    # Several things changed at once: one notification, typed by the most important.
    assert events[1].data["type"] == "connection"
    assert events[1].data["message"] == (
        "Kitchen Robotea: connected, turned off, mode: Standby, off"
    )
    assert set(events[1].data["changes"]) == {"connection", "power", "mode", "status"}


async def test_freshness_warning_and_tags(hass: HomeAssistant, mock_api) -> None:
    events = async_capture_events(hass, "karaca_connect_event")
    entry = await _setup(
        hass,
        mock_api,
        [
            _robotea("brewing", "Çay Demleniyor"),
            _robotea("brewedfresh", "Çayınız Taze", remaining=3600),  # fresh: tagged "started"
            _robotea("brewedfresh", "Çayınız Taze", remaining=630),
            _robotea("brewedfresh", "Çayınız Taze", remaining=598),  # crosses 10 min: warning
            _robotea("brewedfresh", "Çayınız Taze", remaining=568),  # same window: no repeat
            _robotea("brewedstale", "Çay Bayatladı"),  # tagged "ended"
        ],
    )
    for _ in range(5):
        await _poll(hass, entry)

    assert [(e.data["type"], e.data["freshness"], e.data["message"]) for e in events] == [
        ("status", "started", "Kitchen Robotea: tea is brewed"),
        ("freshness", "ending", "Kitchen Robotea: tea stays fresh for 10 more minutes"),
        ("status", "ended", "Kitchen Robotea: tea is no longer fresh"),
    ]
    assert events[1].data["remaining_seconds"] == 598


async def test_no_warning_when_starting_below_threshold(hass: HomeAssistant, mock_api) -> None:
    """HA (re)started with under 10 minutes left: no warning, no fake crossing."""
    events = async_capture_events(hass, "karaca_connect_event")
    entry = await _setup(
        hass,
        mock_api,
        [
            _robotea("brewedfresh", "Çayınız Taze", remaining=500),
            _robotea("brewedfresh", "Çayınız Taze", remaining=470),
        ],
    )
    await _poll(hass, entry)
    assert events == []


async def test_full_tea_cycle_messages(hass: HomeAssistant, mock_api) -> None:
    """The cycle observed live on a Robotea Pro 4in1."""
    events = async_capture_events(hass, "karaca_connect_event")
    entry = await _setup(
        hass,
        mock_api,
        [
            _robotea("off", "Kapalı", mode="standby"),
            _robotea("waterboiling", "Su Kaynıyor"),
            _robotea("brewing", "Çay Demleniyor"),
            _robotea("brewedfresh", "Çayınız Taze", remaining=3600),
        ],
    )
    for _ in range(3):
        await _poll(hass, entry)
    assert [e.data["message"] for e in events] == [
        "Kitchen Robotea: mode: Tea brewing, water is boiling for tea",
        "Kitchen Robotea: tea brewing started",
        "Kitchen Robotea: tea is brewed",
    ]
