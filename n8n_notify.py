#!/usr/bin/env python3
"""
n8n Integration — Schickt Lead-Ergebnisse an einen n8n Webhook.

Nutzung:
    python n8n_notify.py output/leads_20260404.json

Damit kannst du in n8n einen Workflow bauen, der:
- Die Leads in Google Sheets schreibt
- Dir eine Telegram/Slack-Benachrichtigung schickt
- Automatisch E-Mails an HOT Leads verschickt (via Brevo)
"""

import sys
import json
import os
import requests
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# n8n Webhook URL — Setze diese in config/.env oder als Environment-Variable
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")


def send_to_n8n(json_path: str, webhook_url: str = ""):
    """Schickt die Lead-Ergebnisse an n8n Webhook."""
    
    url = webhook_url or N8N_WEBHOOK_URL
    if not url:
        logger.error("Kein N8N_WEBHOOK_URL gesetzt! Setze es in config/.env")
        sys.exit(1)
    
    # JSON laden
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Zusammenfassung erstellen
    prospects = data.get("prospects", [])
    hot_leads = [p for p in prospects if p.get("priority") == "🔥 HOT"]
    warm_leads = [p for p in prospects if p.get("priority") == "⭐ WARM"]
    
    payload = {
        "source": "lead-finder",
        "generated_at": data.get("generated_at"),
        "summary": {
            "total": len(prospects),
            "hot": len(hot_leads),
            "warm": len(warm_leads),
        },
        # Nur HOT und WARM Leads an n8n schicken
        "hot_leads": [
            {
                "name": p.get("name"),
                "address": p.get("full_address", p.get("address", "")),
                "phone": p.get("phone", ""),
                "email": (p.get("emails_found", [None]) or [None])[0],
                "website": p.get("website", ""),
                "rating": p.get("rating", 0),
                "reviews": p.get("review_count", 0),
                "score": p.get("score", 0),
                "distance_km": p.get("distance_km", 0),
                "google_maps": p.get("google_maps_url", ""),
                "social": p.get("social_links", {}),
                "has_booking": p.get("has_booking_system", False),
            }
            for p in hot_leads
        ],
        "warm_leads": [
            {
                "name": p.get("name"),
                "address": p.get("full_address", p.get("address", "")),
                "phone": p.get("phone", ""),
                "email": (p.get("emails_found", [None]) or [None])[0],
                "website": p.get("website", ""),
                "score": p.get("score", 0),
                "google_maps": p.get("google_maps_url", ""),
            }
            for p in warm_leads
        ],
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        logger.info(f"✅ Erfolgreich an n8n gesendet: {len(hot_leads)} HOT, {len(warm_leads)} WARM Leads")
    except requests.RequestException as e:
        logger.error(f"❌ Fehler beim Senden an n8n: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Nutzung: python n8n_notify.py output/leads_DATUM.json")
        sys.exit(1)
    
    send_to_n8n(sys.argv[1])
