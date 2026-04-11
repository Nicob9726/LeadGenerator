#!/usr/bin/env python3
"""
Telegram Benachrichtigung — schickt die Top 5 Leads nach jedem Lauf.
"""

import os
import csv
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(token: str, chat_id: str, text: str):
    url = TELEGRAM_API.format(token=token)
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=15)
    resp.raise_for_status()


def load_top_leads(csv_path: Path, n: int = 5) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    # Nur HOT und WARM, sortiert nach Score
    relevant = [l for l in leads if l.get("priority") in ("HOT", "WARM")]
    relevant.sort(key=lambda l: int(l.get("score", 0)), reverse=True)
    return relevant[:n]


def format_message(leads: list[dict], csv_path: Path) -> str:
    date_str = Path(csv_path).stem.replace("leads_", "")
    lines = [f"<b>🔍 Lead Finder — Top {len(leads)} Leads</b>"]
    lines.append(f"<i>Lauf vom {date_str}</i>\n")

    for i, lead in enumerate(leads, 1):
        priority = "🔥" if lead.get("priority") == "HOT" else "⭐"
        name = lead.get("name", "–")
        address = lead.get("address", "–")
        phone = lead.get("phone", "")
        website = lead.get("website", "")
        score = lead.get("score", "?")
        rating = lead.get("rating", "")
        reviews = lead.get("review_count", "")
        hours = lead.get("opening_hours", "")

        lines.append(f"{priority} <b>{i}. {name}</b>  [Score: {score}]")
        lines.append(f"📍 {address}")
        if rating and reviews:
            lines.append(f"⭐ {rating} ({reviews} Bewertungen)")
        if phone:
            lines.append(f"📞 {phone}")
        if website:
            lines.append(f"🌐 {website}")
        if hours:
            # Nur erste 2 Tage anzeigen damit es nicht zu lang wird
            days = hours.split(" | ")[:2]
            lines.append(f"🕐 {' | '.join(days)}")
        lines.append("")

    return "\n".join(lines)


def notify(csv_path: Path):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID nicht gesetzt — keine Benachrichtigung")
        return

    leads = load_top_leads(csv_path)
    if not leads:
        logger.info("Keine HOT/WARM Leads — keine Telegram-Nachricht")
        return

    message = format_message(leads, csv_path)
    send_telegram(token, chat_id, message)
    logger.info(f"✅ Telegram: Top {len(leads)} Leads verschickt")


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / "config" / ".env")
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Nutzung: python telegram_notify.py output/leads_DATUM.csv")
        sys.exit(1)

    notify(Path(sys.argv[1]))
