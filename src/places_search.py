"""
Google Places API Suche nach Massagepraxen und Physiotherapeuten.
"""

import math
import time
import logging
import requests

logger = logging.getLogger(__name__)

BOOKING_SYSTEMS = [
    "treatwell", "shore", "doctolib", "timify", "calendly", "acuity",
    "clinq", "cituro", "terminland", "samedi", "phorest", "fresha",
    "mindbody", "booksy", "simplybook", "termin-direkt", "setmore",
    "appointy", "10to8", "reserve.google", "bookingkit", "ebuero",
    "appointlet", "zocdoc", "jameda",
]

SEARCH_KEYWORDS = [
    "Massagepraxis",
    "Massage",
    "Physiotherapie",
    "Wellness Massage",
    "Thai Massage",
    "Osteopathie",
]


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Berechnet Distanz in km zwischen zwei GPS-Koordinaten."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


class PlacesSearcher:
    BASE_URL = "https://maps.googleapis.com/maps/api/place"

    def __init__(self, api_key: str, lat: float, lng: float, radius_km: int = 50,
                 verbose: bool = False):
        self.api_key = api_key
        self.lat = lat
        self.lng = lng
        self.radius_m = radius_km * 1000
        self.verbose = verbose

    def _generate_grid(self) -> list[tuple]:
        """Teilt den Suchradius in überlappende Kreise auf (max 25km pro Kreis)."""
        radius_km = self.radius_m / 1000
        if radius_km <= 25:
            return [(self.lat, self.lng)]

        points = [(self.lat, self.lng)]
        ring_distance_km = 20
        num_rings = math.ceil(radius_km / ring_distance_km)

        for ring in range(1, num_rings + 1):
            ring_radius_km = min(ring * ring_distance_km, radius_km)
            num_points = max(6, ring * 6)
            for j in range(num_points):
                angle = (2 * math.pi * j) / num_points
                delta_lat = (ring_radius_km * math.cos(angle)) / 111.0
                delta_lng = (ring_radius_km * math.sin(angle)) / (111.0 * math.cos(math.radians(self.lat)))
                points.append((self.lat + delta_lat, self.lng + delta_lng))

        return points

    def _nearby_search(self, keyword: str, lat: float, lng: float, page_token: str = None) -> dict:
        search_radius = min(self.radius_m, 25000)  # max 25km pro Einzelsuche
        params = {
            "location": f"{lat},{lng}",
            "radius": search_radius,
            "keyword": keyword,
            "language": "de",
            "key": self.api_key,
        }
        if page_token:
            params["pagetoken"] = page_token
        resp = requests.get(f"{self.BASE_URL}/nearbysearch/json", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _place_details(self, place_id: str) -> dict:
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,geometry,opening_hours",
            "language": "de",
            "key": self.api_key,
        }
        resp = requests.get(f"{self.BASE_URL}/details/json", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("result", {})

    def search_all(self, keywords: list = None) -> list[dict]:
        """Sucht mit allen Keywords an allen Gitterpunkten und dedupliziert Ergebnisse."""
        keywords = keywords or SEARCH_KEYWORDS
        grid = self._generate_grid()
        seen_ids = set()
        places = []

        logger.info(f"Suchgitter: {len(grid)} Punkte × {len(keywords)} Keywords")

        for keyword in keywords:
            for point_idx, (lat, lng) in enumerate(grid):
                logger.info(f"Suche '{keyword}' [{point_idx+1}/{len(grid)}] bei ({lat:.3f}, {lng:.3f})")
                page_token = None
                page = 0

                while True:
                    if page_token:
                        time.sleep(2)  # Google braucht kurze Pause vor page_token

                    data = self._nearby_search(keyword, lat, lng, page_token)
                    status = data.get("status")

                    if status not in ("OK", "ZERO_RESULTS"):
                        logger.warning(f"API Status '{status}' für '{keyword}'")
                        break

                    for result in data.get("results", []):
                        pid = result["place_id"]
                        if pid not in seen_ids:
                            seen_ids.add(pid)
                            places.append(result)

                    page_token = data.get("next_page_token")
                    page += 1
                    if not page_token or page >= 3:
                        break

                time.sleep(0.2)

        logger.info(f"{len(places)} einzigartige Orte gefunden")
        return places

    def enrich_with_details(self, places: list[dict]) -> list[dict]:
        """Holt Details (Telefon, Website, Rating) für jeden Ort."""
        enriched = []
        for i, place in enumerate(places):
            pid = place["place_id"]
            if self.verbose:
                logger.info(f"Details [{i+1}/{len(places)}]: {place.get('name', '?')}")

            details = self._place_details(pid)
            loc = place.get("geometry", {}).get("location", {})
            dist = haversine_distance(
                self.lat, self.lng,
                loc.get("lat", 0), loc.get("lng", 0)
            )

            enriched.append({
                "place_id": pid,
                "name": details.get("name") or place.get("name", ""),
                "address": details.get("formatted_address") or place.get("vicinity", ""),
                "phone": details.get("formatted_phone_number", ""),
                "website": details.get("website", ""),
                "rating": details.get("rating") or place.get("rating", 0),
                "review_count": details.get("user_ratings_total") or place.get("user_ratings_total", 0),
                "lat": loc.get("lat", 0),
                "lng": loc.get("lng", 0),
                "distance_km": round(dist, 1),
                "opening_hours": " | ".join(details.get("opening_hours", {}).get("weekday_text", [])),
            })
            time.sleep(0.1)  # sanftes Rate-Limiting

        return enriched
