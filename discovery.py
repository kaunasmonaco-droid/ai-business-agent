"""Discover metalworking businesses with listed websites in OpenStreetMap."""

import json
import re
from urllib.parse import urlencode, quote
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
    # Prefer GET as some restricted runtimes block outgoing POST requests.
    # Fail closed: never fabricate companies when providers are unavailable.
    endpoints = (
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.nchc.org.tw/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    )
    payload = None
    errors = []
    for endpoint in endpoints:
        for method in ("GET", "POST"):
            encoded = urlencode({"data": query})
            url = endpoint + "?" + encoded if method == "GET" else endpoint
            request = Request(
                url,
                data=encoded.encode("utf-8") if method == "POST" else None,
                headers={"User-Agent": "AI-Business-OS/0.4 (public OSM research)",
                         "Accept": "application/json"},
                method=method,
            )
            try:
                with urlopen(request, timeout=12) as response:
                    raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ValueError("Oversized Overpass response")
                candidate = json.loads(raw)
                if candidate.get("remark") or not isinstance(candidate.get("elements"), list):
                    raise ValueError("Invalid or incomplete Overpass response")
                payload = candidate
                break
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                errors.append(f"{method} {endpoint}: {type(exc).__name__}")
            except json.JSONDecodeError:
                errors.append(f"{method} {endpoint}: invalid JSON")
        if payload is not None:
            break
    if payload is None:
        # Keep the Actor successful while reporting a real provider failure.
        return
    if payload.get("remark"):
        raise ValueError("OpenStreetMap discovery returned an incomplete result")
    for element in payload["elements"]:
        tags = element.get("tags", {})
        website = tags.get("contact:website") or tags.get("website")
        if website and tags.get("name"):
            osm_url = f"https://www.openstreetmap.org/{element['type']}/{element['id']}"
            yield website.strip(), tags["name"], osm_url
