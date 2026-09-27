#!/usr/bin/env python3
"""Fetch one day from the panel and print JSON shapes (no secrets logged)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path

from bot.services.normalize import normalize_payload
from bot.services.panel import PanelClient


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--out", default="data/panel-dump")
    args = parser.parse_args()
    day = date.fromisoformat(args.day)

    client = PanelClient(
        base_url=os.getenv("PANEL_BASE_URL", "https://panel.exbot.su"),
        refresh_token=os.getenv("PANEL_REFRESH_NOW")
        or os.getenv("PANEL_REFRESH_TOKEN", ""),
        access_token=os.getenv("PANEL_ACCESS_NOW")
        or os.getenv("PANEL_ACCESS_TOKEN", ""),
        server_id=int(os.getenv("SERVER_ID", "6")),
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report = await client.fetch_report_log(day)
    faq = await client.fetch_player_requests_z(day)
    (out / f"report-{day}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / f"faq-{day}.json").write_text(
        json.dumps(faq, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_cards = normalize_payload(report, "Report")
    faq_cards = normalize_payload(faq, "FAQ")
    print(f"report cards: {len(report_cards)}")
    print(f"faq cards: {len(faq_cards)}")
    if report_cards:
        print("sample report:", report_cards[0])
    if faq_cards:
        print("sample faq:", faq_cards[0])


if __name__ == "__main__":
    asyncio.run(main())
