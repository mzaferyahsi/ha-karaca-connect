# Karaca Connect for Home Assistant (unofficial)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/mzaferyahsi/ha-karaca-connect/actions/workflows/validate.yml/badge.svg)](https://github.com/mzaferyahsi/ha-karaca-connect/actions/workflows/validate.yml)

Custom integration for Karaca Connect devices: **Robotea** tea/coffee machines and
**AeroFritas** air fryers. It talks to the same cloud API as the official
Karaca Connect Android app; there is no local API.

> Unofficial, reverse-engineered from the Android app for interoperability.
> The API can change without notice. Use at your own risk.

## Install

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mzaferyahsi&repository=ha-karaca-connect&category=integration)

1. In HACS, open the ⋮ menu → **Custom repositories**, add
   `https://github.com/mzaferyahsi/ha-karaca-connect` with type **Integration**.
2. Search for **Karaca Connect**, download it, and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Karaca Connect**, then sign in
   with your Karaca Connect app email and password.

### Manual

Copy `custom_components/karaca_connect` into your Home Assistant `config/custom_components/`,
restart, then add the integration as above.

Polling interval: 30 s.

## Entities

| Device | Entity | Source field |
|---|---|---|
| All | `binary_sensor` Connected | `meta.connected` |
| All | `event` Activity | fires on connection / power / mode / status changes (see Notifications) |
| Robotea | `sensor` Mode, Mode state, Status, Countdown, Tea freshness | `detail.modeName`, `modeStateLabel`, `stepView.label`, time until `freshness.end` (computed like the official app), shown as `m:ss` (`0:00` when no countdown; exact seconds in the `remaining_seconds` attribute), `freshness.level` |
| Robotea | `sensor` Fresh until (timestamp) | `freshness.end` (else `stepView.countdown.endTime`), read in Home Assistant's time zone like the official app |
| Robotea | `sensor` State (disabled by default) | `detail.state` (raw integer) |
| Robotea | `sensor` Kettle temperature / target (only if reported) | `kettleTemperatureRead` / `kettleTemperatureSet` |
| Robotea | `switch` Power | `detail.modes.standBy.active`. This is the app's main power button: on means the machine is on; turning it off powers the Robotea down. |
| Robotea | `switch` Tea brewing / Boiling water / Filter coffee / Baby food / Herbal tea / Kettle | `detail.modes.<key>.active`. A switch is only created for modes the device reports (not null). |
| AeroFritas | `sensor` State, Mode, Temperature, Remaining time, Cook time | `detail.state`, `modeName`, `temperature`, `remainingTimeInSeconds`, `time` |
| AeroFritas | `button` Stop / Pause / Continue | `POST /api/v1/airfryer/cmd/{cmd}` |
| AeroFritas | service `karaca_connect.start_cooking` | `POST /api/v1/airfryer/cmd/start` |

The air fryer *Mode* sensor exposes `available_modes` (id, name, default
temperature, default time) to use with `start_cooking`:

```yaml
action: karaca_connect.start_cooking
data:
  device_id: <your air fryer device>
  mode_id: 3
  temperature: 180
  time: "15:00"      # likely mm:ss; copy the format shown in available_modes[].time
```

## Notifications

Every Karaca device has an **Activity** event entity. Whenever a device's connection, power,
mode or status changes, it fires one event (typed `connection`, `power`, `mode` or `status`, the
most important change first) with a ready-made `message`, for example
`Remziye: Fresh (Çayınız Taze)`. The same data is fired on the event bus as
`karaca_connect_event`, so one automation covers every Karaca device:

```yaml
alias: Karaca notifications
triggers:
  - trigger: event
    event_type: karaca_connect_event
actions:
  - action: notify.all_devices   # or notify.mobile_app_<your_phone>
    data:
      title: Karaca
      message: "{{ trigger.event.data.message }}"
mode: queued
```

Event data: `type`, `message`, `device_name`, `device_id`, `kind`, `changes`, `previous`,
`current`, `status_text`. The state Home Assistant starts up in is a baseline and is not reported.
Tea freshness level steps are not reported, to keep notifications quiet.

## Testing against your account

`tools/probe.py` uses the integration's own API client. It prompts for your
password and never prints tokens.

```bash
pip install aiohttp
python3 tools/probe.py you@example.com
python3 tools/probe.py you@example.com --raw
```

## Protocol notes

Recovered by static analysis of `com.btpro.clients.karacaconnect` 2.0.3 (versionCode 65,
APK SHA-256 `76b3c09d…3e13`) and re-checked against 2.0.6 (versionCode 70, APK SHA-256
`747070c9…0d71`). Both are signed with certificate SHA-256 `3a2b32c4…8ddc` and declare the
same 43 endpoints. Unless marked as observed live, what follows is what the app's Retrofit
interface and models declare.

**Base URL:** `https://karacaconnectapi.krc.com.tr`

**Headers:** `Authorization: Bearer <jwToken>`,
`User-Agent: Android <ver>; device: <manufacturer> <model>; version 2.0.3`,
`Accept-Language: <lang>` (app default `tr`).

**Envelope:** most responses are `{"succeeded": bool, "messages": [..], "data": T}`.
Errors may also carry `message`, `error_description`, `custom_error`, `errorCode`.
HTTP 503 means maintenance.

### Auth
| Method | Path | Body → Response |
|---|---|---|
| POST | `api/auth/signin` | `{email, password}` → `{succeeded, messages, data{id, userName, email, roles, isVerified, jwToken, refreshToken}}` (the success message "Giriş başarılı" was observed live; the `data` shape is still from static analysis) |
| POST | `api/auth/refresh-token` | `{refreshToken}` → envelope `data: SignInData`. The app calls this from its OkHttp authenticator on 401. |
| POST | `api/auth/signout` | `{refreshToken, pushToken}` |
| GET/POST | `api/auth/profile` | profile |

### Devices
| Method | Path | Notes |
|---|---|---|
| GET | `api/v1/devices/me` | `[{id, udid, label, pin, modelNumber, serialNumber, type, product{id, code, name, category, images}}]`. A `type` containing `robotea` means Robotea. |
| POST / DELETE | `api/v1/devices/me` | add or remove by `{udid}` |
| GET | `api/v1/devices/{id}` | Robotea `{id, udid, label, name, meta{connected, activated}, schedules[], detail: Robotea}` |
| PATCH | `api/v1/devices/{id}` | rename `{label}` |
| PUT | `api/v1/devices/{id}/modes/{modeId}` | `{active: bool}`. `modeId` is the numeric `mode` of a `detail.modes` entry; the app hardcodes `1` for standby. |
| GET | `api/v1/devices/{did}/settings` | `{notifications: [{id, label, value, imageUrl}]}` |
| PUT | `api/v1/devices/{did}/settings/{id}` | `{value: bool}` |
| POST | `api/v1/devices/{did}/lock` / `unlock` | child lock `{password, pin}` |
| GET/POST | `api/v1/devices/{id}/schedules` | `ScheduleRequest{days[], label, mode, notify, tempSet, time, timeSet, timeZone}` |
| GET/PUT/PATCH/DELETE | `api/v1/devices/{did}/schedules/{id}` | PATCH body `{active}` |
| GET | `api/v1/products/robotea/{deviceId}/usage/{mode}?range=` | usage graph |

`Robotea`, as observed live on a Robotea Pro 4in1 (`type: "robotea4in1"`, model `V00`):

```json
{
  "updatedDate": "2026-11-23T23:40:56.288137",
  "state": 1, "mode": 9, "modeName": "teabrewing",
  "modeState": 4, "modeStateLabel": "brewedfresh",
  "stepView": {"id": "teabrewing_brewedfresh", "label": "Çayınız Taze",
               "countdown": {"startTime": "…", "endTime": "…", "remainingSeconds": 2088,
                             "displayText": "Kalan Tazelik Süresi"}},
  "freshness": {"show": true, "level": 3, "start": "…", "end": "…", "info": "…"},
  "kettleTemperatureSet": null, "kettleTemperatureRead": null,
  "ramadanPlanActive": false, "ramadanPlans": null,
  "modes": {
    "standBy":      {"mode": 1,  "name": "StandBy",      "active": true},
    "filterCoffee": {"mode": 2,  "name": "FilterCoffee", "active": false},
    "boilingWater": {"mode": 6,  "name": "BoilingWater", "active": false},
    "teaBrewing":   {"mode": 9,  "name": "TeaBrewing",   "active": true, "freshness": null},
    "babyFood":     {"mode": 13, "name": "BabyFood",     "active": false},
    "schedule":     {"mode": 99, "name": "Schedule",     "active": false},
    "herbalTea": null, "kettleMode": null
  },
  "activeHerbalTeaMode": null
}
```

Several fields here (`modeStateLabel`, `stepView`, kettle temperatures, `herbalTea`, `kettleMode`)
are newer than the app 2.0.3 models.

**Time zone:** timestamps carry no offset. Like the official app, the integration reads them in
Home Assistant's time zone, and the Countdown counts down to `freshness.end` the same way the app does.

### AeroFritas (air fryer)
| Method | Path | Notes |
|---|---|---|
| GET | `api/v1/products/aerofritas/devices/{id}` | `{…, meta, detail: AirFryer}` |
| POST | `api/v1/airfryer/cmd/start` | `{deviceId, mode{id, label, temp, time}}` |
| POST | `api/v1/airfryer/cmd/stop` / `pause` / `continue` | `{deviceId}` |
| GET/POST | `api/v1/devices/{deviceId}/aerofritas-modes` | custom programs (multipart: temperature, time, name, description, shakeIsActive, shakeTime, image) |
| PUT/DELETE | `api/v1/devices/{deviceId}/aerofritas-modes/{modeId}` | |
| GET | `api/v1/products/aerofritas/{deviceId}/usage[/by-modes\|/by-general\|/by-frequency]` | statistics |

`AirFryer` = `{mode, modeName, state, temperature, time, remainingTimeInSeconds, updateTime,
activeMode, modes[{id, name, description, image, temperature{value, validation{min, max}}, time{value, validation{min, max}}}]}`

### Not used
Recipes come from a separate service, `https://dcx-api.karaca.com/api/request/`. BLE is used only
for Wi-Fi provisioning when adding a device. The app has no MQTT or WebSocket client,
so state must be polled.

## Unknowns

- The full list of `modeStateLabel` values. Only `brewedfresh` ("Fresh") and `brewedstale` ("Stale")
  have been observed. Neither the 2.0.3 nor the 2.0.6 app reads this field, so the list must come from
  live observation. Unknown values are shown split into words (e.g. `waterboiled` → "Water boiled"),
  with the raw code kept in the `raw` attribute.
- What the Robotea `state` integer means. The only numeric check in the app is `modeState == 2` while
  boiling water, which shows "Su Kaynadı" (water boiled).
- What `freshness.level` means. It went 3 → 1 while fresh, then 5 once stale.
- Writes (mode switches, air fryer commands) have not been exercised against the live API yet.
- The exact `time` string format for `start_cooking`. Copy it from `available_modes`.
- The server-side rate limits.
