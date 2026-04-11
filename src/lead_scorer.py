"""
Lead Scoring - Bewertet jeden Prospect nach Priorität.
Je höher der Score, desto wahrscheinlicher wird er dein Kunde.
"""

import logging
from math import radians, cos, sin, asin, sqrt

logger = logging.getLogger(__name__)

# ============================================
# Scoring-Regeln
# ============================================

SCORING_RULES = {
    # Buchungssystem-Status (wichtigstes Kriterium)
    "kein_buchungssystem":       +10,  # Kernzielgruppe!
    "hat_buchungssystem":        -15,  # Nicht interessant (erstmal)
    
    # Website-Status
    "keine_website":              +3,  # Sehr analog = viel Bedarf
    "website_nicht_erreichbar":   +1,  # Evtl. schlecht gewartet
    "nur_telefon":                +5,  # Klar analoger Prozess
    "hat_kontaktformular":        +1,  # Minimal digital
    
    # Bewertungen (Indikator für Etabliertheit & Budget)
    "bewertungen_ueber_50":       +5,
    "bewertungen_30_bis_50":      +3,
    "bewertungen_10_bis_30":      +1,
    "bewertungen_unter_10":       +0,
    
    # Bewertungsqualität
    "rating_ueber_4_5":           +3,
    "rating_4_0_bis_4_5":         +1,
    "rating_unter_4_0":           -1,
    
    # Online-Präsenz
    "hat_social_media":           +2,  # Online-affin
    "hat_email_auf_website":      +1,  # Kontaktierbar
    
    # Entfernung
    "innerhalb_15km":             +3,  # Vor-Ort-Besuch sehr leicht
    "innerhalb_30km":             +2,  # Vor-Ort möglich
    "innerhalb_50km":             +1,  # Vor-Ort mit Aufwand
    "ueber_50km":                 +0,  # Nur remote
}


def score_leads(
    prospects: list[dict],
    center_lat: float = 49.2389,
    center_lng: float = 9.1008,
) -> list[dict]:
    """
    Bewertet alle Prospects und sortiert nach Score (höchster zuerst).
    """
    logger.info(f"Scoring von {len(prospects)} Prospects...")
    
    for p in prospects:
        score = 0
        reasons = []
        
        # 1. Buchungssystem
        if p.get("has_booking_system"):
            score += SCORING_RULES["hat_buchungssystem"]
            reasons.append(f"Hat Buchungssystem ({p.get('booking_system_name', '?')}): {SCORING_RULES['hat_buchungssystem']}")
        else:
            score += SCORING_RULES["kein_buchungssystem"]
            reasons.append(f"KEIN Buchungssystem: +{SCORING_RULES['kein_buchungssystem']}")
        
        # 2. Website-Status
        if not p.get("website"):
            score += SCORING_RULES["keine_website"]
            reasons.append(f"Keine Website: +{SCORING_RULES['keine_website']}")
        elif not p.get("website_reachable"):
            score += SCORING_RULES["website_nicht_erreichbar"]
            reasons.append(f"Website nicht erreichbar: +{SCORING_RULES['website_nicht_erreichbar']}")
        
        if p.get("has_phone_only") or (not p.get("website") and p.get("phone")):
            score += SCORING_RULES["nur_telefon"]
            reasons.append(f"Nur Telefon: +{SCORING_RULES['nur_telefon']}")
        
        if p.get("has_contact_form"):
            score += SCORING_RULES["hat_kontaktformular"]
            reasons.append(f"Hat Kontaktformular: +{SCORING_RULES['hat_kontaktformular']}")
        
        # 3. Bewertungen
        reviews = p.get("review_count", 0)
        if reviews >= 50:
            score += SCORING_RULES["bewertungen_ueber_50"]
            reasons.append(f"50+ Bewertungen: +{SCORING_RULES['bewertungen_ueber_50']}")
        elif reviews >= 30:
            score += SCORING_RULES["bewertungen_30_bis_50"]
            reasons.append(f"30-50 Bewertungen: +{SCORING_RULES['bewertungen_30_bis_50']}")
        elif reviews >= 10:
            score += SCORING_RULES["bewertungen_10_bis_30"]
            reasons.append(f"10-30 Bewertungen: +{SCORING_RULES['bewertungen_10_bis_30']}")
        
        # 4. Rating
        rating = p.get("rating", 0)
        if rating >= 4.5:
            score += SCORING_RULES["rating_ueber_4_5"]
            reasons.append(f"Rating ≥4.5: +{SCORING_RULES['rating_ueber_4_5']}")
        elif rating >= 4.0:
            score += SCORING_RULES["rating_4_0_bis_4_5"]
            reasons.append(f"Rating 4.0-4.5: +{SCORING_RULES['rating_4_0_bis_4_5']}")
        elif rating > 0:
            score += SCORING_RULES["rating_unter_4_0"]
            reasons.append(f"Rating <4.0: {SCORING_RULES['rating_unter_4_0']}")
        
        # 5. Online-Präsenz
        if p.get("social_links"):
            score += SCORING_RULES["hat_social_media"]
            reasons.append(f"Social Media: +{SCORING_RULES['hat_social_media']}")
        
        if p.get("emails_found"):
            score += SCORING_RULES["hat_email_auf_website"]
            reasons.append(f"E-Mail gefunden: +{SCORING_RULES['hat_email_auf_website']}")
        
        # 6. Entfernung
        if p.get("lat") and p.get("lng"):
            dist = _haversine(center_lat, center_lng, p["lat"], p["lng"])
            p["distance_km"] = round(dist, 1)
            
            if dist <= 15:
                score += SCORING_RULES["innerhalb_15km"]
                reasons.append(f"Innerhalb 15km: +{SCORING_RULES['innerhalb_15km']}")
            elif dist <= 30:
                score += SCORING_RULES["innerhalb_30km"]
                reasons.append(f"Innerhalb 30km: +{SCORING_RULES['innerhalb_30km']}")
            elif dist <= 50:
                score += SCORING_RULES["innerhalb_50km"]
                reasons.append(f"Innerhalb 50km: +{SCORING_RULES['innerhalb_50km']}")
        
        p["score"] = score
        p["score_reasons"] = reasons
        
        # Kategorie zuweisen
        if score >= 20:
            p["priority"] = "🔥 HOT"
        elif score >= 10:
            p["priority"] = "⭐ WARM"
        elif score >= 0:
            p["priority"] = "❄️ COLD"
        else:
            p["priority"] = "⛔ SKIP"
    
    # Nach Score sortieren
    prospects.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # Statistik
    hot = sum(1 for p in prospects if p.get("priority") == "🔥 HOT")
    warm = sum(1 for p in prospects if p.get("priority") == "⭐ WARM")
    cold = sum(1 for p in prospects if p.get("priority") == "❄️ COLD")
    skip = sum(1 for p in prospects if p.get("priority") == "⛔ SKIP")
    
    logger.info(f"\nScoring-Ergebnis:")
    logger.info(f"  🔥 HOT  (Score ≥20): {hot}")
    logger.info(f"  ⭐ WARM (Score 10-19): {warm}")
    logger.info(f"  ❄️ COLD (Score 0-9): {cold}")
    logger.info(f"  ⛔ SKIP (Score <0): {skip}")
    
    return prospects


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Berechnet die Entfernung zwischen zwei Koordinaten in km."""
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    return 2 * 6371 * asin(sqrt(a))
