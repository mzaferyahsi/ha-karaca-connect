"""Fixtures: payloads shaped after the app's Gson models (serialized @SerializedName keys)."""

import pytest
from aioresponses import aioresponses

BASE = "https://karacaconnectapi.krc.com.tr"

SIGNIN = {
    "succeeded": True,
    "messages": ["Giriş başarılı"],
    "data": {"id": "u1", "email": "a@b.c", "jwToken": "jwt-1", "refreshToken": "rt-1"},
}

DEVICES = {
    "succeeded": True,
    "data": [
        {"id": 11, "udid": "UDID11", "label": "Kitchen Robotea", "type": "robotea4in1",
         "modelNumber": "V00", "serialNumber": "00000000",
         "product": {"id": 3, "code": "robotea4in1", "name": "Çaysever Robotea Pro"}},
        {"id": 22, "udid": "UDID22", "label": "Air Fryer", "type": "aerofritas",
         "modelNumber": "AF1", "serialNumber": "S22", "product": {"name": "Aero Fritas"}},
    ],
}

# Shape observed live from a Robotea Pro 4in1 (identifiers replaced).
ROBOTEA = {
    "succeeded": True,
    "data": {
        "id": 11, "udid": "UDID11", "label": "Kitchen Robotea", "type": "robotea4in1",
        "meta": {"connected": True, "activated": False},
        "schedules": [],
        "detail": {
            "updatedDate": "2026-11-23T23:40:56.288137",
            "state": 1, "mode": 9, "modeName": "teabrewing",
            "modeState": 4, "modeStateLabel": "brewedfresh",
            "stepView": {
                "id": "teabrewing_brewedfresh", "label": "Çayınız Taze",
                "countdown": {
                    "startTime": "2026-11-23T23:40:56.288136",
                    "endTime": "2026-11-24T00:40:56.288136",
                    "remainingSeconds": 2088, "displayText": "Kalan Tazelik Süresi",
                },
            },
            "freshness": {"show": True, "level": 3, "start": "2026-11-23T23:40:56.288136",
                          "end": "2026-11-24T00:40:56.288136", "info": "Tazelik"},
            "kettleTemperatureSet": None, "kettleTemperatureRead": None,
            "ramadanPlanActive": False, "ramadanPlans": None,
            "modes": {
                "standBy": {"mode": 1, "name": "StandBy", "active": True},
                "filterCoffee": {"mode": 2, "name": "FilterCoffee", "active": False},
                "boilingWater": {"mode": 6, "name": "BoilingWater", "active": False},
                "babyFood": {"mode": 13, "name": "BabyFood", "active": False},
                "teaBrewing": {"mode": 9, "name": "TeaBrewing", "active": True, "freshness": None},
                "schedule": {"mode": 99, "name": "Schedule", "active": False},
                "herbalTea": None, "kettleMode": None,
            },
            "activeHerbalTeaMode": None,
        },
    },
}

AIRFRYER = {
    "succeeded": True,
    "data": {
        "id": 22, "meta": {"connected": False},
        "detail": {
            "mode": 5, "modeName": "Fries", "state": "COOKING", "temperature": 180,
            "time": "15:00", "remainingTimeInSeconds": "420",
            "modes": [{"id": 5, "name": "Fries", "temperature": {"value": 180}, "time": {"value": "15:00"}}],
        },
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_api():
    with aioresponses() as m:
        yield m


def add_cloud(m, robotea=ROBOTEA, repeat=True):
    m.post(f"{BASE}/api/auth/signin", payload=SIGNIN, repeat=repeat)
    m.get(f"{BASE}/api/v1/devices/me", payload=DEVICES, repeat=repeat)
    m.get(f"{BASE}/api/v1/devices/11", payload=robotea, repeat=repeat)
    m.get(f"{BASE}/api/v1/products/aerofritas/devices/22", payload=AIRFRYER, repeat=repeat)
