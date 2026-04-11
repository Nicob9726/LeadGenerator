#!/usr/bin/env python3
"""
Lead Finder — Massagepraxen ohne Buchungssystem finden.

Verwendung:
    python main.py                          # Standard (50km um Bad Rappenau)
    python main.py --radius 15             # Kleinerer Radius
    python main.py --skip-website-check    # Nur Google Maps, kein Website-Check
    python main.py --input output/x.csv   # Website-Check für bestehende CSV
    python main.py --output massage_hn     # Benutzerdefinierter Output-Name
    python main.py -v                      # Ausführliche Logs
"""

import os
import csv
import json
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from src.places_search import PlacesSearcher
from src.website_analyzer import analyze_website
from src.lead_scorer import score_all

load_dotenv(Path(__file__).parent / "config" / ".env")


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stdout,
    )


def parse_args():
    p = argparse.ArgumentParser(description="Lead Finder — Massagepraxen ohne Buchungssystem")
    p.add_argument("--radius", type=int, default=None,
                   help="Suchradius in km (Standard: aus .env oder 50)")
    p.add_argument("--skip-website-check", action="store_true",
                   help="Kein Website-Besuch (schneller, spart Ressourcen)")
    p.add_argument("--input", type=str, default=None,
                   help="Bestehende CSV als Input statt Google Maps Suche")
    p.add_argument("--output", type=str, default=None,
                   help="Output-Dateiname ohne Endung (Standard: leads_DATUM)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Ausführliche Logs")
    return p.parse_args()


def load_from_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_seen_ids(output_dir: Path) -> set:
    """Lädt alle place_ids die in früheren Läufen bereits gefunden wurden."""
    seen_file = output_dir / "seen_leads.txt"
    if not seen_file.exists():
        return set()
    return set(seen_file.read_text(encoding="utf-8").splitlines())


def save_seen_ids(output_dir: Path, new_ids: list[str]):
    """Fügt neue place_ids zur gesehen-Liste hinzu."""
    seen_file = output_dir / "seen_leads.txt"
    existing = load_seen_ids(output_dir)
    all_ids = existing | set(new_ids)
    seen_file.write_text("\n".join(sorted(all_ids)), encoding="utf-8")


def save_results(leads: list[dict], output_dir: Path, base_name: str):
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / f"{base_name}.csv"
    json_path = output_dir / f"{base_name}.json"

    fieldnames = [
        "priority_display", "score", "name", "address", "phone", "email",
        "website", "rating", "review_count", "distance_km",
        "has_booking_system", "booking_system_name", "has_contact_form",
        "has_social_media", "score_reasons", "opening_hours", "place_id",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2, default=str)

    return csv_path, json_path


def print_summary(leads: list[dict]):
    hot  = [l for l in leads if l["priority"] == "HOT"]
    warm = [l for l in leads if l["priority"] == "WARM"]
    cold = [l for l in leads if l["priority"] == "COLD"]
    skip = [l for l in leads if l["priority"] == "SKIP"]

    print("\n" + "="*50)
    print("ZUSAMMENFASSUNG")
    print("="*50)
    print(f"  🔥 HOT  : {len(hot):3d}  (sofort kontaktieren)")
    print(f"  ⭐ WARM : {len(warm):3d}  (E-Mail Outreach)")
    print(f"  ❄️  COLD : {len(cold):3d}  (später)")
    print(f"  ⛔ SKIP : {len(skip):3d}  (hat Buchungssystem)")
    print(f"  ─────────────────")
    print(f"  Gesamt  : {len(leads):3d}")
    print()
    if hot:
        print("TOP 5 HOT Leads:")
        for l in hot[:5]:
            print(f"  [{l['score']:2d}] {l['name']} — {l['address'][:40]}")
    print()


def main():
    args = parse_args()
    setup_logging(args.verbose)
    log = logging.getLogger(__name__)

    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not api_key and not args.input:
        print("FEHLER: GOOGLE_PLACES_API_KEY nicht gesetzt.")
        print("Trage ihn in config/.env ein (Vorlage: config/.env.example)")
        sys.exit(1)

    lat   = float(os.getenv("SEARCH_LAT", "49.2333"))
    lng   = float(os.getenv("SEARCH_LNG", "9.1000"))
    radius = args.radius or int(os.getenv("SEARCH_RADIUS_KM", "50"))

    base_name = args.output or f"leads_{datetime.now().strftime('%Y%m%d_%H%M')}"
    output_dir = Path(__file__).parent / "output"

    # --- Schritt 1: Orte laden ---
    if args.input:
        log.info(f"Lade Leads aus: {args.input}")
        raw_places = load_from_csv(args.input)
    else:
        log.info(f"Starte Google Maps Suche ({radius}km Radius um {lat},{lng})")
        searcher = PlacesSearcher(api_key, lat, lng, radius, verbose=args.verbose)
        raw_results = searcher.search_all()

        # Bereits gesehene Praxen rausfiltern
        seen_ids = load_seen_ids(output_dir)
        new_results = [r for r in raw_results if r["place_id"] not in seen_ids]
        log.info(f"{len(raw_results)} gefunden, {len(raw_results) - len(new_results)} bereits bekannt, {len(new_results)} neu")

        if not new_results:
            log.info("Keine neuen Praxen gefunden — alle wurden bereits in früheren Läufen entdeckt.")
            sys.exit(0)

        log.info(f"Hole Details für {len(new_results)} neue Orte ...")
        raw_places = searcher.enrich_with_details(new_results)

    # --- Schritt 2: Website-Check ---
    if args.skip_website_check:
        log.info("Website-Check übersprungen (--skip-website-check)")
        places = [
            {**p, "has_booking_system": False, "booking_system_name": "",
             "has_contact_form": False, "has_social_media": False, "email": ""}
            for p in raw_places
        ]
    else:
        log.info(f"Analysiere {len(raw_places)} Websites ...")
        places = []
        for place in tqdm(raw_places, desc="Website-Check", unit="Praxis"):
            website = place.get("website", "")
            analysis = analyze_website(website)
            if analysis.get("error") and args.verbose:
                log.debug(f"  {place.get('name', '?')}: {analysis['error']}")
            places.append({**place, **analysis})

    # --- Schritt 3: Scoring ---
    log.info("Bewerte Leads ...")
    scored = score_all(places)

    # --- Schritt 4: Speichern ---
    csv_path, json_path = save_results(scored, output_dir, base_name)
    log.info(f"CSV  → {csv_path}")
    log.info(f"JSON → {json_path}")

    # Gefundene IDs als "gesehen" markieren
    save_seen_ids(output_dir, [p["place_id"] for p in scored if p.get("place_id")])

    print_summary(scored)


if __name__ == "__main__":
    main()
