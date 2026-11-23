"""Async client for the Karaca Connect cloud API.

Recovered by static analysis of the Karaca Connect Android app 2.0.3
(com.btpro.clients.karacaconnect). This module has no Home Assistant
dependencies so it can also be used from tools/probe.py.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://karacaconnectapi.krc.com.tr"
# The app sends "Android <release>; device: <manufacturer> <model>; version 2.0.3".
USER_AGENT = "Android 14; device: HomeAssistant KaracaConnect; version 2.0.3"
TIMEOUT = aiohttp.ClientTimeout(total=30)


class KaracaError(Exception):
    """Generic API error."""


class KaracaAuthError(KaracaError):
    """Credentials or tokens were rejected."""


class KaracaConnectionError(KaracaError):
    """The API could not be reached."""


@dataclass
class Tokens:
    """Access and refresh tokens returned by sign-in / refresh."""

    access_token: str
    refresh_token: str | None


def device_kind(device_type: str | None) -> str:
    """Classify a device from the `type` field of GET /api/v1/devices/me.

    The app treats a type containing "robotea" as a Robotea; the other
    connected product it supports is the AeroFritas air fryer.
    """
    t = (device_type or "").lower()
    if "robotea" in t:
        return "robotea"
    return "airfryer"


class KaracaApi:
    """Minimal async client; one instance per account."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        language: str = "en",
        tokens: Tokens | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._language = language
        self._tokens = tokens
        self._auth_lock = asyncio.Lock()

    @property
    def tokens(self) -> Tokens | None:
        return self._tokens

    # ---------------------------------------------------------------- auth

    async def sign_in(self) -> Tokens:
        """POST api/auth/signin -> SignInResponse{succeeded, messages, data{jwToken, refreshToken}}.

        The Kotlin field is `signInData` but its Gson name is "data".
        """
        body = await self._raw(
            "POST",
            "api/auth/signin",
            json={"email": self._email, "password": self._password},
            auth=False,
        )
        if not isinstance(body, dict) or not body.get("succeeded"):
            raise KaracaAuthError(_messages(body) or "Sign-in failed")
        data = body.get("data") or body.get("signInData") or {}
        if not isinstance(data, dict) or not data.get("jwToken"):
            keys = sorted(data) if isinstance(data, dict) else type(data).__name__
            raise KaracaError(f"Sign-in succeeded but no jwToken in response (data keys: {keys})")
        self._tokens = Tokens(data["jwToken"], data.get("refreshToken"))
        return self._tokens

    async def _refresh(self) -> Tokens:
        """POST api/auth/refresh-token {refreshToken} -> BaseResponse<SignInData>.

        Falls back to a full sign-in when there is no refresh token or it is rejected.
        """
        if self._tokens and self._tokens.refresh_token:
            try:
                body = await self._raw(
                    "POST",
                    "api/auth/refresh-token",
                    json={"refreshToken": self._tokens.refresh_token},
                    auth=False,
                )
                data = (body or {}).get("data") or {}
                if body and body.get("succeeded") and data.get("jwToken"):
                    self._tokens = Tokens(
                        data["jwToken"],
                        data.get("refreshToken") or self._tokens.refresh_token,
                    )
                    return self._tokens
            except KaracaAuthError:
                pass
            _LOGGER.debug("Refresh token rejected; signing in again")
        return await self.sign_in()

    # ------------------------------------------------------------- transport

    async def _raw(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        auth: bool = True,
    ) -> Any:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": self._language,
            "Accept": "application/json",
        }
        if auth and self._tokens:
            headers["Authorization"] = f"Bearer {self._tokens.access_token}"
        url = f"{BASE_URL}/{path.lstrip('/')}"
        try:
            async with self._session.request(
                method, url, json=json, headers=headers, timeout=TIMEOUT
            ) as resp:
                text = await resp.text()
                payload: Any = None
                if text:
                    try:
                        payload = await resp.json(content_type=None)
                    except ValueError:
                        payload = None
                if resp.status in (401, 403):
                    raise KaracaAuthError(_messages(payload) or f"HTTP {resp.status}")
                if resp.status == 503:
                    raise KaracaConnectionError("Karaca Connect is in maintenance (HTTP 503)")
                if resp.status >= 400:
                    raise KaracaError(
                        f"{method} {path}: HTTP {resp.status} {_messages(payload) or text[:200]}"
                    )
                return payload
        except (TimeoutError, aiohttp.ClientError) as err:
            raise KaracaConnectionError(f"{method} {path}: {err}") from err

    async def _request(self, method: str, path: str, *, json: Any = None) -> Any:
        """Authenticated request; refreshes once on 401 like the app's OkHttp authenticator."""
        if self._tokens is None or not self._tokens.access_token:
            async with self._auth_lock:
                if self._tokens is None:
                    await self.sign_in()
                elif not self._tokens.access_token:
                    # Restored from a saved refresh token after a restart.
                    await self._refresh()
        stale = self._tokens
        try:
            body = await self._raw(method, path, json=json)
        except KaracaAuthError:
            async with self._auth_lock:
                if self._tokens is stale:
                    await self._refresh()
            body = await self._raw(method, path, json=json)
        return body

    async def _data(self, method: str, path: str, *, json: Any = None) -> Any:
        """Unwrap BaseResponse<T>{succeeded, messages, data}."""
        body = await self._request(method, path, json=json)
        if isinstance(body, dict) and "succeeded" in body:
            if body.get("succeeded") is False:
                raise KaracaError(_messages(body) or f"{method} {path} failed")
            return body.get("data")
        return body

    # ------------------------------------------------------------- devices

    async def list_devices(self) -> list[dict[str, Any]]:
        """GET api/v1/devices/me -> [DeviceData{id, udid, label, type, modelNumber, serialNumber, product}]."""
        return await self._data("GET", "api/v1/devices/me") or []

    async def get_robotea(self, device_id: int | str) -> dict[str, Any]:
        """GET api/v1/devices/{id} -> DeviceDetailData{detail: Robotea, meta{connected, activated}, ...}."""
        return await self._data("GET", f"api/v1/devices/{device_id}") or {}

    async def set_robotea_mode(self, device_id: int | str, mode_id: int | str, active: bool) -> Any:
        """PUT api/v1/devices/{id}/modes/{modeId} {active}.

        modeId is the numeric `mode` of an entry under detail.modes (standby is "1" in the app).
        """
        return await self._data(
            "PUT", f"api/v1/devices/{device_id}/modes/{mode_id}", json={"active": active}
        )

    async def get_airfryer(self, device_id: int | str) -> dict[str, Any]:
        """GET api/v1/products/aerofritas/devices/{id} -> CookDeviceDetailData{detail: AirFryer, ...}."""
        return await self._data("GET", f"api/v1/products/aerofritas/devices/{device_id}") or {}

    async def airfryer_start(
        self, device_id: int, mode_id: int, temperature: int, time: str, label: str | None = None
    ) -> Any:
        """POST api/v1/airfryer/cmd/start {deviceId, mode{id, label, temp, time}}.

        `time` uses the same string format the server returns in the mode's time.value.
        """
        mode: dict[str, Any] = {"id": mode_id, "temp": temperature, "time": time}
        if label is not None:
            mode["label"] = label
        return await self._data(
            "POST", "api/v1/airfryer/cmd/start", json={"deviceId": device_id, "mode": mode}
        )

    async def airfryer_command(self, device_id: int, command: str) -> Any:
        """POST api/v1/airfryer/cmd/{stop|pause|continue} {deviceId}."""
        if command not in ("stop", "pause", "continue"):
            raise ValueError(f"Unknown air fryer command {command!r}")
        return await self._data(
            "POST", f"api/v1/airfryer/cmd/{command}", json={"deviceId": device_id}
        )

    async def get_settings(self, device_id: int | str) -> dict[str, Any]:
        """GET api/v1/devices/{did}/settings -> {notifications: [{id, label, value}]}."""
        return await self._data("GET", f"api/v1/devices/{device_id}/settings") or {}


def _messages(body: Any) -> str:
    if isinstance(body, dict):
        msgs = body.get("messages") or body.get("Messages")
        if isinstance(msgs, list):
            return "; ".join(str(m) for m in msgs if m)
        # Error body (com.btpro.core.remote.exception.Error) also carries these.
        for key in ("message", "error_description", "custom_error", "errorCode", "title"):
            if body.get(key):
                return str(body[key])
    return ""
