#!/usr/bin/env python3
"""
Lead Finder - Hauptskript
==========================
Findet Massagepraxen ohne Buchungssystem in deiner Region.

Nutzung:
    python main.py                          # Voller Durchlauf
    python main.py --radius 30              # 30km Radius
    python main.py --skip-website-check     # Nur Google Maps, kein Website-Check
    python main.py --input existing.csv     # Website-Check für bestehende Liste
    python main.py --output meine_leads     # Custom Output-Name

Ergebnis: CSV + JSON Dateien in ./output/
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Module importieren
from src.places_search import search_places
from src.website_analyzer import analyze_websites
from src.lead_scorer import score_leads

# ============================================
# Konfiguration
# ============================================

DEFAULT_CONFIG = {
    "api_key": os.environ.get("GOOGLE_PLACES_API_KEY", ""),
    "queries": [
        "Massagepraxis",
        "Massage Studio",
        "Thai Massage",
        "Wellness Massage",
        "Physiotherapie Massage",
    ],
    "center_lat": 49.2389,   # Bad Rappenau
    "center_lng": 9.1008,
    "radius_km": 50,
    "request_timeout": 10,
    "max_concurrent": 5,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "output_dir": "./output",
}


def load_config() -> dict:
    """Lädt Konfiguration aus .env Datei oder Environment."""
    config = DEFAULT_CONFIG.copy()
    
    # .env Datei laden falls vorhanden
    env_file = Path("config/.env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
    
    # Aus Environment übernehmen
    if os.environ.get("GOOGLE_PLACES_API_KEY"):
        config["api_key"] = os.environ["GOOGLE_PLACES_API_KEY"]
    if os.environ.get("SEARCH_QUERIES"):
        config["queries"] = [q.strip() for q in os.environ["SEARCH_QUERIES"].split(",")]
    if os.environ.get("SEARCH_CENTER_LAT"):
        config["center_lat"] = float(os.environ["SEARCH_CENTER_LAT"])
    if os.environ.get("SEARCH_CENTER_LNG"):
        config["center_lng"] = float(os.environ["SEARCH_CENTER_LNG"])
    if os.environ.get("SEARCH_RADIUS_KM"):
        config["radius_km"] = int(os.environ["SEARCH_RADIUS_KM"])
    
    return config


def load_existing_csv(filepath: str) -> list[dict]:
    """Lädt eine bestehende CSV-Datei als Prospect-Liste."""
    prospects = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Numerische Felder konvertieren
            for field in ["lat", "lng", "rating", "review_count", "score", "distance_km"]:
                if field in row and row[field]:
                    try:
                        row[field] = float(row[field])
                        if field in ["review_count", "score"]:
                            row[field] = int(row[field])
                    except ValueError:
                        pass
            # Boolean Felder
            for field in ["has_booking_system", "website_reachable", "has_contact_form"]:
                if field in row:
                    row[field] = row[field].lower() in ("true", "1", "ja", "yes")
            prospects.append(row)
    
    logging.info(f"  {len(prospects)} Prospects aus {filepath} geladen")
    return prospects


def save_results(prospects: list[dict], output_dir: str, output_name: str = ""):
    """Speichert die Ergebnisse als CSV und JSON."""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = output_name or f"leads_{timestamp}"
    
    # === CSV Export ===
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    
    csv_fields = [
        "priority", "score", "name", "full_address", "distance_km",
        "phone", "website", "rating", "review_count",
        "has_booking_system", "booking_system_name",
        "emails_found", "social_links",
        "google_maps_url", "score_reasons", "opening_hours",
    ]
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        
        for p in prospects:
            row = p.copy()
            # Listen/Dicts zu Strings für CSV
            if isinstance(row.get("emails_found"), list):
                row["emails_found"] = "; ".join(row["emails_found"])
            if isinstance(row.get("social_links"), dict):
                row["social_links"] = "; ".join(f"{k}: {v}" for k, v in row["social_links"].items())
            if isinstance(row.get("score_reasons"), list):
                row["score_reasons"] = " | ".join(row["score_reasons"])
            if isinstance(row.get("booking_keywords"), list):
                row["booking_keywords"] = "; ".join(row["booking_keywords"])
            if isinstance(row.get("opening_hours"), list):
                row["opening_hours"] = " | ".join(row["opening_hours"])
            writer.writerow(row)
    
    logging.info(f"\n✅ CSV gespeichert: {csv_path}")
    
    # === JSON Export (für n8n / Weiterverarbeitung) ===
    json_path = os.path.join(output_dir, f"{base_name}.json")
    
    # Nur die wichtigsten Felder für JSON
    json_data = {
        "generated_at": datetime.now().isoformat(),
        "total_prospects": len(prospects),
        "hot_leads": sum(1 for p in prospects if p.get("priority") == "🔥 HOT"),
        "warm_leads": sum(1 for p in prospects if p.get("priority") == "⭐ WARM"),
        "prospects": prospects,
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
    
    logging.info(f"✅ JSON gespeichert: {json_path}")
    
    # === Zusammenfassung in Terminal ===
    print("\n" + "=" * 70)
    print("  LEAD FINDER — ERGEBNIS")
    print("=" * 70)
    
    hot = [p for p in prospects if p.get("priority") == "🔥 HOT"]
    warm = [p for p in prospects if p.get("priority") == "⭐ WARM"]
    
    print(f"\n  Gesamt gefunden:  {len(prospects)}")
    print(f"  🔥 HOT Leads:     {len(hot)}")
    print(f"  ⭐ WARM Leads:    {len(warm)}")
    
    if hot:
        print(f"\n  TOP 10 HOT LEADS:")
        print(f"  {'Score':>5}  {'Bewertungen':>11}  {'Name':<40}  {'Ort'}")
        print(f"  {'-'*5}  {'-'*11}  {'-'*40}  {'-'*30}")
        for p in hot[:10]:
            name = (p.get('name', '') or '')[:40]
            addr = (p.get('full_address', '') or p.get('address', ''))[:30]
            print(f"  {p.get('score', 0):>5}  {p.get('review_count', 0):>11}  {name:<40}  {addr}")
    
    print(f"\n  Dateien: {csv_path}")
    print(f"           {json_path}")
    print("=" * 70)
    
    return csv_path, json_path


def main():
    parser = argparse.ArgumentParser(
        description="Lead Finder — Findet Massagepraxen ohne Buchungssystem"
    )
    parser.add_argument("--radius", type=int, help="Suchradius in km (default: 50)")
    parser.add_argument("--skip-website-check", action="store_true",
                       help="Überspringe Website-Analyse (nur Google Maps Daten)")
    parser.add_argument("--input", type=str,
                       help="Bestehende CSV laden (überspringt Google Maps Suche)")
    parser.add_argument("--output", type=str, default="",
                       help="Output-Dateiname (ohne Endung)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Ausführliche Ausgabe")
    
    args = parser.parse_args()
    
    # Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    
    config = load_config()
    
    if args.radius:
        config["radius_km"] = args.radius
    
    print("\n" + "=" * 70)
    print("  🔍 LEAD FINDER — Massagepraxen ohne Buchungssystem finden")
    print("=" * 70)
    print(f"  Zentrum:  Bad Rappenau ({config['center_lat']}, {config['center_lng']})")
    print(f"  Radius:   {config['radius_km']} km")
    print(f"  Suchen:   {', '.join(config['queries'])}")
    print("=" * 70 + "\n")
    
    # ==========================================
    # SCHRITT 1: Prospects finden
    # ==========================================
    if args.input:
        print(f"📂 Lade bestehende Liste: {args.input}")
        prospects = load_existing_csv(args.input)
    else:
        if not config["api_key"]:
            print("❌ FEHLER: Kein Google Places API Key gefunden!")
            print("   Setze GOOGLE_PLACES_API_KEY in config/.env oder als Environment-Variable.")
            print("   Anleitung: https://console.cloud.google.com/apis/credentials")
            sys.exit(1)
        
        print("📍 Schritt 1/3: Massagepraxen auf Google Maps suchen...")
        prospects = search_places(
            api_key=config["api_key"],
            queries=config["queries"],
            center_lat=config["center_lat"],
            center_lng=config["center_lng"],
            radius_km=config["radius_km"],
        )
        
        if not prospects:
            print("⚠️ Keine Ergebnisse gefunden. Prüfe API Key und Suchparameter.")
            sys.exit(1)
        
        print(f"   ✅ {len(prospects)} Praxen gefunden\n")
    
    # ==========================================
    # SCHRITT 2: Websites analysieren
    # ==========================================
    if not args.skip_website_check:
        print("🌐 Schritt 2/3: Websites auf Buchungssysteme prüfen...")
        prospects = analyze_websites(
            prospects,
            timeout=config["request_timeout"],
            max_concurrent=config["max_concurrent"],
            user_agent=config["user_agent"],
        )
        print(f"   ✅ Website-Analyse abgeschlossen\n")
    else:
        print("⏭️  Website-Check übersprungen\n")
        for p in prospects:
            p["has_booking_system"] = False
            p["booking_system_name"] = ""
    
    # ==========================================
    # SCHRITT 3: Lead Scoring
    # ==========================================
    print("📊 Schritt 3/3: Lead Scoring...")
    prospects = score_leads(
        prospects,
        center_lat=config["center_lat"],
        center_lng=config["center_lng"],
    )
    
    # ==========================================
    # ERGEBNISSE SPEICHERN
    # ==========================================
    save_results(prospects, config["output_dir"], args.output)


if __name__ == "__main__":
    main()
