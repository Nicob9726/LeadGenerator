#!/usr/bin/env python3
"""
Importiert HOT/WARM Leads als Zeilen in eine Notion-Datenbank.

Beim ersten Aufruf wird die Datenbank automatisch erstellt und die ID
in config/.env gespeichert. Danach werden nur neue Leads hinzugefügt.
"""

import json
import os
import sys
import glob
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent / "config" / ".env"
load_dotenv(ENV_PATH)

log = logging.getLogger(__name__)

NOTION_TOKEN       = os.getenv("NOTION_TOKEN", "")
NOTION_PAGE_ID     = os.getenv("NOTION_PAGE_ID", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")
NOTION_VERSION     = "2022-06-28"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def create_database(parent_page_id: str) -> str:
    """Erstellt die Lead-Datenbank unter der angegebenen Seite."""
    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "🔥"},
        "title": [{"type": "text", "text": {"content": "Lead Finder — Massagepraxen"}}],
        "properties": {
            "Name": {"title": {}},
            "Priorität": {
                "select": {
                    "options": [
                        {"name": "🔥 HOT",  "color": "red"},
                        {"name": "⭐ WARM", "color": "yellow"},
                        {"name": "❄️ COLD", "color": "blue"},
                        {"name": "⛔ SKIP", "color": "gray"},
                    ]
                }
            },
            "Status": {
                "select": {
                    "options": [
                        {"name": "Neu",              "color": "blue"},
                        {"name": "Kontaktiert",      "color": "yellow"},
                        {"name": "Antwort erhalten", "color": "orange"},
                        {"name": "Kein Interesse",   "color": "red"},
                        {"name": "Abschluss",        "color": "green"},
                    ]
                }
            },
            "Score":           {"number": {"format": "number"}},
            "Telefon":         {"phone_number": {}},
            "E-Mail":          {"email": {}},
            "Website":         {"url": {}},
            "Adresse":         {"rich_text": {}},
            "Entfernung (km)": {"number": {"format": "number"}},
            "Bewertungen":     {"number": {"format": "number"}},
            "Rating":          {"number": {"format": "number"}},
            "Buchungssystem":  {"checkbox": {}},
            "Notizen":         {"rich_text": {}},
            "Place ID":        {"rich_text": {}},
        },
    }
    resp = requests.post(
        "https://api.notion.com/v1/databases",
        headers=_headers(), json=body, timeout=30,
    )
    resp.raise_for_status()
    db_id = resp.json()["id"]
    log.info(f"Notion-Datenbank erstellt: {db_id}")
    return db_id


def _save_database_id(db_id: str):
    """Schreibt NOTION_DATABASE_ID in config/.env."""
    content = ENV_PATH.read_text(encoding="utf-8")
    if "NOTION_DATABASE_ID=" in content:
        lines = [
            f"NOTION_DATABASE_ID={db_id}" if l.startswith("NOTION_DATABASE_ID=") else l
            for l in content.splitlines()
        ]
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        ENV_PATH.write_text(content.rstrip() + f"\nNOTION_DATABASE_ID={db_id}\n", encoding="utf-8")


def get_existing_place_ids(database_id: str) -> set:
    """Gibt alle Place IDs zurück die bereits in der DB vorhanden sind."""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    ids = set()
    cursor = None

    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(url, headers=_headers(), json=body, timeout=30)
        if resp.status_code != 200:
            break
        data = resp.json()
        for page in data.get("results", []):
            rt = page.get("properties", {}).get("Place ID", {}).get("rich_text", [])
            if rt:
                ids.add(rt[0]["text"]["content"])
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return ids


def _add_lead(database_id: str, lead: dict):
    """Fügt einen einzelnen Lead als Zeile in die Datenbank ein."""
    priority_map = {
        "HOT":  "🔥 HOT",
        "WARM": "⭐ WARM",
        "COLD": "❄️ COLD",
        "SKIP": "⛔ SKIP",
    }
    priority = lead.get("priority", "COLD")
    website  = (lead.get("website") or "").strip()
    email    = (lead.get("email")   or "").strip()
    phone    = (lead.get("phone")   or "").strip()

    props = {
        "Name":           {"title":    [{"text": {"content": lead.get("name", "")}}]},
        "Priorität":      {"select":   {"name": priority_map.get(priority, "❄️ COLD")}},
        "Status":         {"select":   {"name": "Neu"}},
        "Score":          {"number":   lead.get("score", 0)},
        "Adresse":        {"rich_text":[{"text": {"content": (lead.get("address") or "")[:2000]}}]},
        "Entfernung (km)":{"number":   float(lead.get("distance_km") or 0)},
        "Bewertungen":    {"number":   int(lead.get("review_count")  or 0)},
        "Rating":         {"number":   float(lead.get("rating")      or 0)},
        "Buchungssystem": {"checkbox": bool(lead.get("has_booking_system", False))},
        "Place ID":       {"rich_text":[{"text": {"content": lead.get("place_id", "")}}]},
    }

    if website:
        props["Website"] = {"url": website}
    if email:
        props["E-Mail"]  = {"email": email}
    if phone:
        props["Telefon"] = {"phone_number": phone}

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=_headers(),
        json={"parent": {"database_id": database_id}, "properties": props},
        timeout=30,
    )
    resp.raise_for_status()


def _is_existing_database(notion_id: str) -> bool:
    """Prüft ob die ID bereits eine Notion-Datenbank ist."""
    resp = requests.get(
        f"https://api.notion.com/v1/databases/{notion_id}",
        headers=_headers(), timeout=15,
    )
    return resp.status_code == 200


def notify(json_path: Path):
    """
    Hauptfunktion: Importiert HOT/WARM Leads aus der JSON-Datei nach Notion.
    Wird von main.py aufgerufen.
    """
    global NOTION_DATABASE_ID

    if not NOTION_TOKEN:
        log.warning("Notion: NOTION_TOKEN fehlt — überspringe Export.")
        return
    if not NOTION_PAGE_ID and not NOTION_DATABASE_ID:
        log.warning("Notion: NOTION_PAGE_ID fehlt — überspringe Export.")
        return

    # Datenbank-ID auflösen
    if not NOTION_DATABASE_ID:
        # Prüfen ob NOTION_PAGE_ID schon eine Datenbank ist
        if _is_existing_database(NOTION_PAGE_ID):
            log.info("Notion: Vorhandene Datenbank erkannt — nutze direkt.")
            NOTION_DATABASE_ID = NOTION_PAGE_ID
            _save_database_id(NOTION_DATABASE_ID)
        else:
            log.info("Erstelle neue Notion-Datenbank ...")
            NOTION_DATABASE_ID = create_database(NOTION_PAGE_ID)
            _save_database_id(NOTION_DATABASE_ID)

    with open(json_path, encoding="utf-8") as f:
        leads = json.load(f)

    relevant = [l for l in leads if l.get("priority") in ("HOT", "WARM")]
    if not relevant:
        log.info("Notion: Keine HOT/WARM Leads zum Importieren.")
        return

    existing_ids = get_existing_place_ids(NOTION_DATABASE_ID)
    new_leads    = [l for l in relevant if l.get("place_id", "") not in existing_ids]

    log.info(f"Notion: {len(relevant)} HOT/WARM Leads, {len(new_leads)} neu → wird importiert")

    ok = 0
    for lead in new_leads:
        try:
            _add_lead(NOTION_DATABASE_ID, lead)
            ok += 1
        except Exception as e:
            log.warning(f"Notion: Fehler bei '{lead.get('name', '?')}': {e}")

    log.info(f"Notion: {ok}/{len(new_leads)} Leads erfolgreich importiert.")


# --- Direktaufruf ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not NOTION_TOKEN or (not NOTION_PAGE_ID and not NOTION_DATABASE_ID):
        print("FEHLER: NOTION_TOKEN und NOTION_PAGE_ID müssen in config/.env gesetzt sein.")
        sys.exit(1)

    files = sorted(glob.glob("output/*.json"), key=os.path.getmtime, reverse=True)
    if not files:
        print("FEHLER: Keine JSON-Datei in output/ gefunden.")
        sys.exit(1)

    json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(files[0])
    log.info(f"Lade: {json_path}")
    notify(json_path)
