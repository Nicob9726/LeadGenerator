"""
Bewertet und kategorisiert Leads anhand von Kriterien.
"""


SCORING_RULES = [
    # (key, comparator, value, points, label)
    ("has_booking_system", "eq", True,  -15, "Hat Buchungssystem"),
    ("has_booking_system", "eq", False, +10, "Kein Buchungssystem"),
    ("website",            "eq", "",    +3,  "Keine Website"),
    ("has_contact_form",   "eq", False, +5,  "Nur Telefon/kein Formular"),
    ("review_count",       "gte", 50,   +5,  "50+ Bewertungen"),
    ("review_count",       "range", (30, 49), +3, "30-50 Bewertungen"),
    ("rating",             "gte", 4.5,  +3,  "Rating >= 4.5"),
    ("has_social_media",   "eq", True,  +2,  "Social Media vorhanden"),
    ("distance_km",        "lte", 15,   +3,  "Innerhalb 15km"),
    ("distance_km",        "range", (15.1, 30), +2, "Innerhalb 30km"),
]


def _matches(value, comparator, threshold) -> bool:
    if comparator == "eq":
        return value == threshold
    if comparator == "gte":
        return (value or 0) >= threshold
    if comparator == "lte":
        return (value or 0) <= threshold
    if comparator == "range":
        lo, hi = threshold
        return lo <= (value or 0) <= hi
    return False


def score_lead(lead: dict) -> dict:
    """Berechnet Score und Kategorie für einen Lead."""
    score = 0
    reasons = []

    for key, comparator, threshold, points, label in SCORING_RULES:
        if _matches(lead.get(key), comparator, threshold):
            score += points
            reasons.append(f"{'+' if points > 0 else ''}{points}: {label}")

    if score >= 20:
        priority = "HOT"
        emoji = "🔥"
    elif score >= 10:
        priority = "WARM"
        emoji = "⭐"
    elif score >= 0:
        priority = "COLD"
        emoji = "❄️"
    else:
        priority = "SKIP"
        emoji = "⛔"

    return {
        **lead,
        "score": score,
        "priority": priority,
        "priority_display": f"{emoji} {priority}",
        "score_reasons": " | ".join(reasons),
    }


def score_all(leads: list[dict]) -> list[dict]:
    scored = [score_lead(lead) for lead in leads]
    return sorted(scored, key=lambda x: x["score"], reverse=True)
