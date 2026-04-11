"""
Analysiert Websites auf vorhandene Buchungssysteme und Kontaktmöglichkeiten.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BOOKING_SYSTEMS = {
    "treatwell": "Treatwell",
    "shore.com": "Shore",
    "shore.de": "Shore",
    "doctolib": "Doctolib",
    "timify": "Timify",
    "calendly": "Calendly",
    "acuityscheduling": "Acuity",
    "clinq": "Clinq",
    "cituro": "Cituro",
    "terminland": "Terminland",
    "samedi": "Samedi",
    "phorest": "Phorest",
    "fresha": "Fresha",
    "mindbodyonline": "MindBody",
    "booksy": "Booksy",
    "simplybook": "SimplyBook",
    "termin-direkt": "Termin-Direkt",
    "setmore": "Setmore",
    "appointy": "Appointy",
    "10to8": "10to8",
    "reserve.google": "Google Reserve",
    "bookingkit": "BookingKit",
    "zocdoc": "ZocDoc",
    "jameda": "Jameda",
    "appointlet": "Appointlet",
    "ebuero": "eBüro",
}

CONTACT_FORM_PATTERNS = [
    r'<form[^>]*contact',
    r'<form[^>]*anfrage',
    r'<form[^>]*buchung',
    r'contact.?form',
    r'kontakt.?formular',
]

SOCIAL_PATTERNS = {
    "instagram": r'instagram\.com/[^"\'>\s]+',
    "facebook": r'facebook\.com/[^"\'>\s]+',
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def analyze_website(url: str, timeout: int = 10) -> dict:
    """
    Besucht die Website und gibt Analyse-Ergebnisse zurück.

    Returns:
        dict mit keys: has_booking_system, booking_system_name,
                       has_contact_form, has_social_media, email, raw_url
    """
    result = {
        "has_booking_system": False,
        "booking_system_name": "",
        "has_contact_form": False,
        "has_social_media": False,
        "email": "",
        "raw_url": url,
        "error": "",
    }

    if not url:
        result["error"] = "keine Website"
        return result

    # URL normalisieren
    if not url.startswith("http"):
        url = "https://" + url

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout,
                            allow_redirects=True)
        html = resp.text.lower()
        soup = BeautifulSoup(resp.text, "lxml")

        # Buchungssystem-Check (HTML + alle Skript/Link-Tags)
        full_text = html
        for tag in soup.find_all(["script", "link", "iframe", "a"]):
            src = tag.get("src", "") or tag.get("href", "") or tag.get("data-src", "")
            full_text += " " + src.lower()

        for pattern, name in BOOKING_SYSTEMS.items():
            if pattern in full_text:
                result["has_booking_system"] = True
                result["booking_system_name"] = name
                break

        # Kontaktformular
        for pat in CONTACT_FORM_PATTERNS:
            if re.search(pat, html, re.IGNORECASE):
                result["has_contact_form"] = True
                break

        # Social Media
        for _, pat in SOCIAL_PATTERNS.items():
            if re.search(pat, html, re.IGNORECASE):
                result["has_social_media"] = True
                break

        # E-Mail
        email_match = re.search(
            r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
            resp.text
        )
        if email_match:
            result["email"] = email_match.group(0).lower()

    except requests.exceptions.SSLError:
        # Retry mit http://
        try:
            http_url = url.replace("https://", "http://")
            resp = requests.get(http_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            # Inline-Analyse ohne Rekursion
            html = resp.text.lower()
            soup = BeautifulSoup(resp.text, "lxml")
            full_text = html
            for tag in soup.find_all(["script", "link", "iframe", "a"]):
                src = tag.get("src", "") or tag.get("href", "") or tag.get("data-src", "")
                full_text += " " + src.lower()
            for pattern, name in BOOKING_SYSTEMS.items():
                if pattern in full_text:
                    result["has_booking_system"] = True
                    result["booking_system_name"] = name
                    break
        except Exception as e:
            result["error"] = f"SSL + HTTP Fehler: {str(e)[:60]}"
    except requests.exceptions.ConnectionError:
        result["error"] = "Verbindung fehlgeschlagen"
    except requests.exceptions.Timeout:
        result["error"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)[:80]

    return result
