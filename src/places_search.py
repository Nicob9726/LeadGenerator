"""
Google Places API - Massagepraxen finden
Sucht in einem definierten Radius nach Massage/Physio-Praxen
und extrahiert alle relevanten Geschäftsdaten.
"""

import requests
import time
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def search_places(
    api_key: str,
    queries: list[str],
    center_lat: float,
    center_lng: float,
    radius_km: int = 50,
) -> list[dict]:
    """
    Sucht nach Businesses via Google Places API (Nearby Search).
    Teilt große Radien in überlappende Kreise auf für bessere Abdeckung.
    """
    all_places = {}
    
    # Bei großem Radius: Aufteilen in kleinere Suchkreise (max 50km pro Suche)
    search_points = _generate_search_grid(center_lat, center_lng, radius_km)
    
    logger.info(f"Starte Suche mit {len(queries)} Suchbegriffen an {len(search_points)} Punkten")
    
    for query in queries:
        for i, (lat, lng) in enumerate(search_points):
            search_radius = min(radius_km, 25) * 1000  # in Metern, max 50km
            
            logger.info(f"  Suche '{query}' bei ({lat:.4f}, {lng:.4f}), Radius {search_radius}m...")
            
            places = _nearby_search(api_key, query, lat, lng, search_radius)
            
            for place in places:
                pid = place["place_id"]
                if pid not in all_places:
                    all_places[pid] = place
                    
            # Rate limiting: max 10 Requests pro Sekunde
            time.sleep(0.2)
    
    logger.info(f"Insgesamt {len(all_places)} einzigartige Businesses gefunden")
    
    # Details für jeden Place abrufen
    detailed_places = []
    for i, (pid, place) in enumerate(all_places.items()):
        logger.info(f"  Details abrufen [{i+1}/{len(all_places)}]: {place.get('name', 'Unbekannt')}")
        details = _get_place_details(api_key, pid)
        if details:
            merged = {**place, **details}
            detailed_places.append(merged)
        time.sleep(0.15)  # Rate limiting
    
    return detailed_places


def _generate_search_grid(center_lat: float, center_lng: float, radius_km: int) -> list[tuple]:
    """
    Generiert ein Raster von Suchpunkten, um einen großen Radius abzudecken.
    Google Places API liefert max 60 Ergebnisse pro Suche,
    also brauchen wir mehrere überlappende Kreise.
    """
    if radius_km <= 25:
        return [(center_lat, center_lng)]
    
    points = [(center_lat, center_lng)]  # Zentrum immer dabei
    
    # Ringe um das Zentrum erstellen
    ring_distance_km = 20  # Abstand zwischen Ringen
    num_rings = math.ceil(radius_km / ring_distance_km)
    
    for ring in range(1, num_rings + 1):
        ring_radius_km = ring * ring_distance_km
        if ring_radius_km > radius_km:
            ring_radius_km = radius_km
            
        # Punkte auf dem Ring gleichmäßig verteilen
        num_points = max(6, ring * 6)
        for j in range(num_points):
            angle = (2 * math.pi * j) / num_points
            
            # Ungefähre Umrechnung km -> Grad
            delta_lat = (ring_radius_km * math.cos(angle)) / 111.0
            delta_lng = (ring_radius_km * math.sin(angle)) / (111.0 * math.cos(math.radians(center_lat)))
            
            points.append((center_lat + delta_lat, center_lng + delta_lng))
    
    return points


def _nearby_search(
    api_key: str,
    query: str,
    lat: float,
    lng: float,
    radius: int,
) -> list[dict]:
    """
    Führt eine Google Places Nearby Search durch.
    Paginiert automatisch (max 60 Ergebnisse).
    """
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    
    params = {
        "key": api_key,
        "location": f"{lat},{lng}",
        "radius": radius,
        "keyword": query,
        "language": "de",
    }
    
    all_results = []
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"API Status: {data.get('status')} - {data.get('error_message', '')}")
            return []
        
        results = data.get("results", [])
        all_results.extend(_parse_basic_results(results))
        
        # Pagination (Google gibt max 20 pro Seite, bis zu 3 Seiten = 60)
        while "next_page_token" in data and len(all_results) < 60:
            time.sleep(2)  # Google braucht ~2s bis next_page_token gültig ist
            params = {
                "key": api_key,
                "pagetoken": data["next_page_token"],
            }
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            all_results.extend(_parse_basic_results(results))
    
    except requests.RequestException as e:
        logger.error(f"API-Fehler bei Nearby Search: {e}")
    
    return all_results


def _parse_basic_results(results: list) -> list[dict]:
    """Parst die Basis-Ergebnisse der Nearby Search."""
    places = []
    for r in results:
        place = {
            "place_id": r.get("place_id"),
            "name": r.get("name", ""),
            "address": r.get("vicinity", ""),
            "lat": r.get("geometry", {}).get("location", {}).get("lat"),
            "lng": r.get("geometry", {}).get("location", {}).get("lng"),
            "rating": r.get("rating", 0),
            "review_count": r.get("user_ratings_total", 0),
            "types": r.get("types", []),
            "business_status": r.get("business_status", "UNKNOWN"),
        }
        
        # Nur aktive Businesses
        if place["business_status"] == "OPERATIONAL":
            places.append(place)
    
    return places


def _get_place_details(api_key: str, place_id: str) -> Optional[dict]:
    """
    Ruft detaillierte Informationen zu einem Place ab:
    Telefon, Website, Öffnungszeiten, etc.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    
    params = {
        "key": api_key,
        "place_id": place_id,
        "fields": "formatted_phone_number,website,url,opening_hours,formatted_address",
        "language": "de",
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "OK":
            return None
        
        result = data.get("result", {})
        
        return {
            "phone": result.get("formatted_phone_number", ""),
            "website": result.get("website", ""),
            "google_maps_url": result.get("url", ""),
            "full_address": result.get("formatted_address", ""),
            "opening_hours": result.get("opening_hours", {}).get("weekday_text", []),
        }
    
    except requests.RequestException as e:
        logger.error(f"API-Fehler bei Place Details: {e}")
        return None
