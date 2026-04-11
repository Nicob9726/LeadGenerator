#!/usr/bin/env python3
"""
Schickt Lead-Ergebnisse an einen n8n Webhook.

Verwendung:
    python n8n_notify.py output/leads_20240101.json
    python n8n_notify.py output/leads_20240101.json --only-hot
"""

import json
import sys
import argparse
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "config" / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("json_file", help="Pfad zur JSON-Datei mit Leads")
    p.add_argument("--only-hot", action="store_true",
                   help="Nur HOT Leads senden")
    p.add_argument("--webhook", default=None,
                   help="Webhook URL (überschreibt N8N_WEBHOOK_URL aus .env)")
    return p.parse_args()


def main():
    args = parse_args()
    webhook_url = args.webhook or os.getenv("N8N_WEBHOOK_URL", "")

    if not webhook_url:
        print("FEHLER: N8N_WEBHOOK_URL nicht gesetzt (config/.env oder --webhook).")
        sys.exit(1)

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"FEHLER: Datei nicht gefunden: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        leads = json.load(f)

    if args.only_hot:
        leads = [l for l in leads if l.get("priority") == "HOT"]
        log.info(f"Filtere auf HOT: {len(leads)} Leads")

    payload = {
        "source": "lead-finder",
        "file": json_path.name,
        "total": len(leads),
        "hot": sum(1 for l in leads if l.get("priority") == "HOT"),
        "warm": sum(1 for l in leads if l.get("priority") == "WARM"),
        "leads": leads,
    }

    log.info(f"Sende {len(leads)} Leads an n8n ...")
    resp = requests.post(webhook_url, json=payload, timeout=30)
    resp.raise_for_status()
    log.info(f"Gesendet! Status: {resp.status_code}")


if __name__ == "__main__":
    main()
