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


def load_top_leads(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    # Nur HOT und WARM, sortiert nach Score
    relevant = [l for l in leads if l.get("priority") in ("HOT", "WARM")]
    relevant.sort(key=lambda l: int(l.get("score", 0) or 0), reverse=True)
    return relevant


def format_lead(i: int, lead: dict) -> str:
    priority = "🔥" if lead.get("priority") == "HOT" else "⭐"
    lines = []
    lines.append(f"{priority} <b>{i}. {lead.get('name', '–')}</b>  [Score: {lead.get('score', '?')}]")
    lines.append(f"📍 {lead.get('address', '–')}")
    if lead.get("rating") and lead.get("review_count"):
        lines.append(f"⭐ {lead['rating']} ({lead['review_count']} Bewertungen)")
    if lead.get("phone"):
        lines.append(f"📞 {lead['phone']}")
    if lead.get("website"):
        lines.append(f"🌐 {lead['website']}")
    if lead.get("opening_hours"):
        days = lead["opening_hours"].split(" | ")[:2]
        lines.append(f"🕐 {' | '.join(days)}")
    return "\n".join(lines)


def split_into_messages(leads: list[dict], csv_path: Path) -> list[str]:
    """Baut Nachrichten und splittet bei Telegram-Limit (4096 Zeichen)."""
    date_str = Path(csv_path).stem.replace("leads_", "")
    header = f"<b>🔍 Lead Finder — {len(leads)} neue Leads</b>\n<i>Lauf vom {date_str}</i>"

    messages = []
    current = header
    for i, lead in enumerate(leads, 1):
        block = "\n\n" + format_lead(i, lead)
        if len(current) + len(block) > 4000:
            messages.append(current)
            current = block.lstrip()
        else:
            current += block

    if current:
        messages.append(current)

    return messages


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

    messages = split_into_messages(leads, csv_path)
    for msg in messages:
        send_telegram(token, chat_id, msg)
    logger.info(f"✅ Telegram: {len(leads)} Leads in {len(messages)} Nachrichten verschickt")


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / "config" / ".env")
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Nutzung: python telegram_notify.py output/leads_DATUM.csv")
        sys.exit(1)

    notify(Path(sys.argv[1]))
