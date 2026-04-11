"""
Website Analyzer - Prüft ob eine Praxis bereits ein Buchungssystem hat.
Besucht die Website, parst den HTML-Content, und sucht nach
Buchungssystem-Indikatoren.
"""

import requests
import re
import logging
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================
# Buchungssystem-Erkennung
# ============================================

# Keywords die auf ein vorhandenes Buchungssystem hindeuten
BOOKING_KEYWORDS = [
    # Deutsche Begriffe
    "termin buchen",
    "online buchen",
    "jetzt buchen",
    "termin vereinbaren",
    "termin reservieren",
    "online terminbuchung",
    "terminanfrage",
    "termin online",
    "buchung starten",
    "freie termine",
    "termine online",
    "termin-kalender",
    "online-reservierung",
    "jetzt termin",
    "wunschtermin",
    
    # Englische Begriffe (viele Tools sind englisch)
    "book now",
    "book appointment",
    "book online",
    "schedule appointment",
    "booking widget",
]

# Bekannte Buchungssystem-Anbieter (URLs, iframes, Skripte)
BOOKING_SYSTEMS = {
    "treatwell": ["treatwell.de", "treatwell.com", "wahanda.com"],
    "shore": ["shore.com", "shore-app.com"],
    "doctolib": ["doctolib.de", "doctolib.fr"],
    "timify": ["timify.com"],
    "calendly": ["calendly.com"],
    "acuity": ["acuityscheduling.com"],
    "clinq": ["clinq.com"],
    "cituro": ["cituro.com"],
    "terminland": ["terminland.de"],
    "samedi": ["samedi.de"],
    "terminpro": ["terminpro.de"],
    "phorest": ["phorest.com"],
    "fresha": ["fresha.com"],
    "meevo": ["meevo.com"],
    "mindbody": ["mindbodyonline.com", "mindbody.io"],
    "booksy": ["booksy.com"],
    "setmore": ["setmore.com"],
    "square": ["squareup.com/appointments"],
    "appointy": ["appointy.com"],
    "10to8": ["10to8.com"],
    "simplybook": ["simplybook.me"],
    "termin-direkt": ["termin-direkt.de"],
    "google_reserve": ["reserve.google.com", "reserve-with-google"],
}

# Keywords die auf KEIN Buchungssystem hindeuten (nur Kontakt)
CONTACT_ONLY_KEYWORDS = [
    "rufen sie uns an",
    "ruf uns an",
    "telefon",
    "kontaktformular",
    "schreiben sie uns",
    "schreib uns",
    "per e-mail",
    "per mail",
    "whatsapp",
    "nachricht senden",
]


@dataclass
class WebsiteAnalysis:
    """Ergebnis der Website-Analyse."""
    url: str
    is_reachable: bool = False
    has_booking_system: bool = False
    booking_system_name: str = ""
    booking_keywords_found: list = field(default_factory=list)
    has_contact_form: bool = False
    has_phone_only: bool = False
    has_email: bool = False
    emails_found: list = field(default_factory=list)
    has_social_media: bool = False
    social_links: dict = field(default_factory=dict)
    page_title: str = ""
    error: str = ""


def analyze_websites(
    prospects: list[dict],
    timeout: int = 10,
    max_concurrent: int = 5,
    user_agent: str = "Mozilla/5.0",
) -> list[dict]:
    """
    Analysiert die Websites aller Prospects parallel.
    Gibt die Prospects mit zusätzlichen Website-Daten zurück.
    """
    logger.info(f"Starte Website-Analyse für {len(prospects)} Prospects...")
    
    # Nur Prospects mit Website analysieren
    with_website = [p for p in prospects if p.get("website")]
    without_website = [p for p in prospects if not p.get("website")]
    
    logger.info(f"  {len(with_website)} haben eine Website, {len(without_website)} nicht")
    
    # Prospects ohne Website: Direkt als "kein Buchungssystem" markieren
    for p in without_website:
        p["has_booking_system"] = False
        p["booking_system_name"] = ""
        p["booking_keywords"] = []
        p["website_reachable"] = False
        p["has_contact_form"] = False
        p["emails_found"] = []
        p["social_links"] = {}
        p["website_error"] = "Keine Website vorhanden"
    
    # Parallele Website-Analyse
    results = {}
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_url = {}
        for p in with_website:
            url = p["website"]
            future = executor.submit(_analyze_single_website, url, timeout, user_agent)
            future_to_url[future] = url
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                analysis = future.result()
                results[url] = analysis
            except Exception as e:
                logger.error(f"Fehler bei {url}: {e}")
                results[url] = WebsiteAnalysis(url=url, error=str(e))
    
    # Ergebnisse in Prospects einbauen
    for p in with_website:
        url = p["website"]
        analysis = results.get(url, WebsiteAnalysis(url=url))
        
        p["has_booking_system"] = analysis.has_booking_system
        p["booking_system_name"] = analysis.booking_system_name
        p["booking_keywords"] = analysis.booking_keywords_found
        p["website_reachable"] = analysis.is_reachable
        p["has_contact_form"] = analysis.has_contact_form
        p["emails_found"] = analysis.emails_found
        p["social_links"] = analysis.social_links
        p["website_error"] = analysis.error
    
    # Statistik
    total_with_booking = sum(1 for p in prospects if p.get("has_booking_system"))
    total_without = sum(1 for p in prospects if not p.get("has_booking_system"))
    logger.info(f"\nErgebnis: {total_with_booking} MIT Buchungssystem, {total_without} OHNE (= deine Leads!)")
    
    return prospects


def _analyze_single_website(url: str, timeout: int, user_agent: str) -> WebsiteAnalysis:
    """Analysiert eine einzelne Website."""
    analysis = WebsiteAnalysis(url=url)
    
    # URL normalisieren
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
    }
    
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            verify=True,
        )
        response.raise_for_status()
        analysis.is_reachable = True
        
        html = response.text.lower()
        
        # Seitentitel extrahieren
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
        if title_match:
            analysis.page_title = title_match.group(1).strip()[:200]
        
        # 1. Prüfe auf bekannte Buchungssysteme
        for system_name, domains in BOOKING_SYSTEMS.items():
            for domain in domains:
                if domain in html:
                    analysis.has_booking_system = True
                    analysis.booking_system_name = system_name
                    analysis.booking_keywords_found.append(f"[System: {system_name}] {domain}")
                    break
            if analysis.has_booking_system:
                break
        
        # 2. Prüfe auf Buchungs-Keywords
        if not analysis.has_booking_system:
            for keyword in BOOKING_KEYWORDS:
                if keyword in html:
                    analysis.booking_keywords_found.append(keyword)
            
            # Wenn mehrere Keywords gefunden → wahrscheinlich Buchungssystem
            if len(analysis.booking_keywords_found) >= 2:
                analysis.has_booking_system = True
                analysis.booking_system_name = "unbekannt (Keywords)"
            
            # Prüfe auch auf Buchungs-Links/Buttons
            booking_link_patterns = [
                r'href=["\'][^"\']*(?:buchen|booking|termin|appointment|reserve)[^"\']*["\']',
                r'class=["\'][^"\']*(?:booking|buchung|termin)[^"\']*["\']',
                r'id=["\'][^"\']*(?:booking|buchung|termin)[^"\']*["\']',
            ]
            for pattern in booking_link_patterns:
                if re.search(pattern, html):
                    analysis.booking_keywords_found.append(f"[Link/Button] {pattern[:40]}")
                    if not analysis.has_booking_system:
                        # Nur als Buchungssystem werten wenn auch ein Keyword da ist
                        if len(analysis.booking_keywords_found) >= 2:
                            analysis.has_booking_system = True
                            analysis.booking_system_name = "unbekannt (Website-Element)"
        
        # 3. Prüfe auf iframes (viele Buchungssysteme nutzen iframes)
        iframe_matches = re.findall(r'<iframe[^>]*src=["\']([^"\']+)["\']', html)
        for iframe_src in iframe_matches:
            for system_name, domains in BOOKING_SYSTEMS.items():
                for domain in domains:
                    if domain in iframe_src:
                        analysis.has_booking_system = True
                        analysis.booking_system_name = system_name
                        analysis.booking_keywords_found.append(f"[iframe] {iframe_src[:80]}")
        
        # 4. Kontaktformular erkennen
        if re.search(r'<form[^>]*>', html):
            analysis.has_contact_form = True
        
        # 5. E-Mail-Adressen extrahieren
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = list(set(re.findall(email_pattern, html)))
        # Filtere Standard-Emails raus (z.B. von WordPress-Plugins)
        analysis.emails_found = [
            e for e in emails
            if not any(x in e.lower() for x in ["example.com", "wordpress", "wix", "sentry", "google"])
        ][:5]  # Max 5 Emails
        
        # 6. Social Media Links
        social_patterns = {
            "instagram": r'(?:instagram\.com|instagr\.am)/([a-zA-Z0-9_.]+)',
            "facebook": r'facebook\.com/([a-zA-Z0-9.]+)',
            "tiktok": r'tiktok\.com/@([a-zA-Z0-9_.]+)',
        }
        for platform, pattern in social_patterns.items():
            match = re.search(pattern, html)
            if match:
                analysis.has_social_media = True
                analysis.social_links[platform] = match.group(0)
        
        # 7. Prüfe ob NUR Kontakt-Infos vorhanden (kein Buchungssystem)
        contact_keyword_count = sum(1 for kw in CONTACT_ONLY_KEYWORDS if kw in html)
        if contact_keyword_count >= 2 and not analysis.has_booking_system:
            analysis.has_phone_only = True
    
    except requests.Timeout:
        analysis.error = "Timeout"
        logger.warning(f"  Timeout bei {url}")
    except requests.ConnectionError:
        analysis.error = "Verbindungsfehler"
        logger.warning(f"  Verbindungsfehler bei {url}")
    except requests.HTTPError as e:
        analysis.error = f"HTTP {e.response.status_code}"
        logger.warning(f"  HTTP-Fehler bei {url}: {e.response.status_code}")
    except Exception as e:
        analysis.error = str(e)[:100]
        logger.warning(f"  Fehler bei {url}: {e}")
    
    return analysis
