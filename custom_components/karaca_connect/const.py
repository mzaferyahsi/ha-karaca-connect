"""Constants for Karaca Connect."""

from datetime import timedelta

DOMAIN = "karaca_connect"
SCAN_INTERVAL = timedelta(seconds=30)

CONF_REFRESH_TOKEN = "refresh_token"

# Keys under Robotea.detail.modes (DeviceDetailData -> Robotea -> Modes).
# "schedule" (mode 99) is deliberately left out; herbalTea/kettleMode are null on
# the Robotea Pro 4in1 and are only created on models that report them.
ROBOTEA_MODE_KEYS = (
    "teaBrewing",
    "boilingWater",
    "filterCoffee",
    "babyFood",
    "herbalTea",
    "kettleMode",
    "standBy",  # the app's main power button: active = machine on
)

SERVICE_START_COOKING = "start_cooking"
ATTR_MODE_ID = "mode_id"
ATTR_TEMPERATURE = "temperature"
ATTR_TIME = "time"
