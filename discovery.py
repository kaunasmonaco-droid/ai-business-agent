"""Discover metalworking businesses with listed websites in OpenStreetMap."""

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def find_websites(country):
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("discovery_country must be a two-letter uppercase country code")
    query = f"""[out:json][timeout:20];
area["ISO3166-1"="{country}"]["admin_level"="2"]->.country;
(
  nwr["craft"="metal_construction"]["website"](area.country);
  nwr["craft"="metal_construction"]["contact:website"](area.country);
  nwr["industrial"="metal_processing"]["website"](area.country);
  nwr["industrial"="metal_processing"]["contact:website"](area.country);
);
out tags 100;"""
    data = None
    errors = []
    for endpoint in ("https://overpass.kumi.systems/api/interpreter",
                     "https://overpass.nchc.org.tw/api/interpreter",
                     "https://overpass-api.de/api/interpreter"):
        request = Request(endpoint, data=urlencode({"data": query}).encode(),
                          headers={"User-Agent": "AI-Business-OS/0.3",
                                   "Content-Type": "application/x-www-form-urlencoded"},
                          method="POST")
        try:
            with urlopen(request, timeout=30) as response:
                candidate = response.read(1_000_001)
            parsed = json.loads(candidate)
            if len(candidate) > 1_000_000 or parsed.get("remark") or not isinstance(parsed.get("elements"), list):
                raise ValueError("Incomplete or oversized Overpass response")
            data = candidate
            break
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(type(exc).__name__)
    if data is None:
        raise RuntimeError("Overpass discovery unavailable: " + ", ".join(errors))
    if len(data) > 1_000_000:
        raise ValueError("OpenStreetMap discovery response is too large")
    payload = json.loads(data)
    if payload.get("remark"):
        raise ValueError("OpenStreetMap discovery returned an incomplete result")
    for element in payload["elements"]:
        tags = element["tags"]
        website = tags.get("contact:website") or tags.get("website")
        if website and tags.get("name"):
            osm_url = f"https://www.openstreetmap.org/{element['type']}/{element['id']}"
            yield website.strip(), tags["name"], osm_url
