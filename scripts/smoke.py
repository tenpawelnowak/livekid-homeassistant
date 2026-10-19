"""Standalone check of the LiveKid API client: prints response shapes, never values of secrets.

Usage:  pip install aiohttp && LIVEKID_TOKEN='eyJ...' python scripts/smoke.py
"""

import asyncio
import importlib.util
import os
import sys
from datetime import date
from pathlib import Path

import aiohttp

spec = importlib.util.spec_from_file_location(
    "livekid_api", Path(__file__).parent.parent / "custom_components/livekid/api.py"
)
api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_mod)


async def main() -> None:
    token = api_mod.extract_token(os.environ.get("LIVEKID_TOKEN", ""))
    if not token:
        sys.exit("Set LIVEKID_TOKEN")
    today = date.today()
    async with aiohttp.ClientSession() as session:
        api = api_mod.LiveKidApi(session, token)
        print("kid:", api.kid_id, "claims:", sorted(api.claims))
        day = await api.get_presence_day(today)
        print("today:", {k: day.get(k) for k in ("was_present", "absent", "planned_absence", "in", "out", "drop_off", "pick_up")})
        month = await api.get_presence_month(today.year, today.month)
        print("month days:", len(month.get("days", {})))
        print("minutes this month:", await api.get_presence_minutes(today.year, today.month))
        print("days off this year:", len(await api.get_days_off(today.year)))
        bal = await api.get_balance()
        print("balance:", bal and bal.get("balance_numeric"))
        bill = await api.get_latest_bill()
        print("bill:", bill and {k: bill.get(k) for k in ("date", "total", "total_to_pay", "payment_due_date")})


asyncio.run(main())
