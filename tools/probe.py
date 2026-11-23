#!/usr/bin/env python3
"""Probe your Karaca Connect account with the integration's API client.

Read-only by default: signs in, lists devices, and prints each device's detail
so you can check the field names the integration relies on.

    pip install aiohttp
    python3 tools/probe.py you@example.com            # prompts for password
    python3 tools/probe.py you@example.com --raw      # dump full JSON
    python3 tools/probe.py you@example.com --set-mode DEVICE_ID MODE_ID on|off   # Robotea write test

Tokens and the password are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import json
import pathlib
import sys

API_PATH = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "karaca_connect" / "api.py"
spec = importlib.util.spec_from_file_location("karaca_api", API_PATH)
karaca_api = importlib.util.module_from_spec(spec)
sys.modules["karaca_api"] = karaca_api
spec.loader.exec_module(karaca_api)

import aiohttp


def summarize(dev: dict, detail: dict, kind: str) -> None:
    st = detail.get("detail") or {}
    meta = detail.get("meta") or {}
    print(f"\n== {dev.get('label')!r} id={dev.get('id')} type={dev.get('type')!r} -> {kind}")
    print(f"   model={dev.get('modelNumber')} connected={meta.get('connected')} activated={meta.get('activated')}")
    print(f"   mode={st.get('mode')} modeName={st.get('modeName')!r} state={st.get('state')!r}")
    if kind == "robotea":
        for key, m in (st.get("modes") or {}).items():
            if isinstance(m, dict):
                print(f"   mode {key:13} id={m.get('mode')} active={m.get('active')} name={m.get('name')!r}")
        print(f"   freshness={st.get('freshness')}")
    else:
        print(f"   temperature={st.get('temperature')} time={st.get('time')!r} remaining={st.get('remainingTimeInSeconds')}")
        for m in st.get("modes") or []:
            print(
                f"   program id={m.get('id')} name={m.get('name')!r} "
                f"temp={(m.get('temperature') or {}).get('value')} time={(m.get('time') or {}).get('value')!r}"
            )


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("email")
    p.add_argument("--raw", action="store_true", help="print full JSON payloads")
    p.add_argument("--set-mode", nargs=3, metavar=("DEVICE_ID", "MODE_ID", "ON_OFF"))
    args = p.parse_args()
    password = getpass.getpass("Karaca Connect password: ")

    async with aiohttp.ClientSession() as session:
        api = karaca_api.KaracaApi(session, args.email, password)
        try:
            await api.sign_in()
        except karaca_api.KaracaError as err:
            print(f"Sign-in failed: {err}")
            return 1
        print("Signed in.")

        if args.set_mode:
            did, mid, onoff = args.set_mode
            res = await api.set_robotea_mode(did, mid, onoff.lower() in ("on", "1", "true"))
            print(f"set_robotea_mode -> {res!r}")
            return 0

        devices = await api.list_devices()
        print(f"{len(devices)} device(s)")
        for dev in devices:
            kind = karaca_api.device_kind(dev.get("type"))
            try:
                detail = await (api.get_robotea(dev["id"]) if kind == "robotea" else api.get_airfryer(dev["id"]))
            except karaca_api.KaracaError as err:
                print(f"\n== {dev.get('label')!r} id={dev.get('id')}: detail failed: {err}")
                continue
            if args.raw:
                print(json.dumps({"device": dev, "detail": detail}, indent=2, ensure_ascii=False))
            else:
                summarize(dev, detail, kind)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
