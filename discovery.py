"""Discover metalworking businesses with listed websites in OpenStreetMap."""

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
    request = Request(
        "https://overpass-api.de/api/interpreter?" + urlencode({"data": query}),
        headers={"User-Agent": "AI-Business-OS/0.2 (kaunasmonaco-droid/ai-business-agent)"},
    )
    with urlopen(request, timeout=25) as response:
        data = response.read(1_000_001)
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
