"""Discover company websites from public OSM and Wikidata records.

No fabricated leads. Each candidate carries a public source URL.
"""
import json
import re
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

AGENT = "AI-Business-OS/0.5 (public company research; contact via GitHub)"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter")
WIKIDATA = "https://query.wikidata.org/sparql"


def _read_json(url, data=None, timeout=12):
    req = Request(url, data=data, headers={
        "User-Agent": AGENT, "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded" if data else "application/json",
    })
    with urlopen(req, timeout=timeout) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Provider response too large")
    return json.loads(raw)


def _osm(country):
    query = f"""[out:json][timeout:15];
area["ISO3166-1"="{country}"]["admin_level"="2"]->.a;
(
 nwr["craft"~"metal_construction|metalworking|welder"]["website"](area.a);
 nwr["industrial"~"metal_processing|machine_shop|manufacturing"]["website"](area.a);
 nwr["man_made"="works"]["website"](area.a);
 nwr["craft"~"metal_construction|metalworking|welder"]["contact:website"](area.a);
 nwr["industrial"~"metal_processing|machine_shop|manufacturing"]["contact:website"](area.a);
);
out tags 60;"""
    encoded = urlencode({"data": query}).encode()
    errors = []
    for endpoint in OVERPASS:
        try:
            result = _read_json(endpoint, encoded, timeout=19)
            if result.get("remark") or not isinstance(result.get("elements"), list):
                raise ValueError("Incomplete Overpass response")
            for element in result["elements"]:
                tags = element.get("tags", {})
                site = tags.get("contact:website") or tags.get("website")
                if site and tags.get("name"):
                    yield site, tags["name"], f"https://www.openstreetmap.org/{element['type']}/{element['id']}"
            return
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{endpoint}: {type(exc).__name__}")
    raise RuntimeError("; ".join(errors))


def _wikidata(country):
    # P17 is country, P856 is official website. Company classifications and
    # metal-related labels narrow the result; downstream website profiling
    # independently verifies actual relevance.
    query = f"""SELECT DISTINCT ?item ?itemLabel ?website WHERE {{
      ?country wdt:P297 "{country}".
      ?item wdt:P17 ?country; wdt:P856 ?website.
      ?item (wdt:P31/wdt:P279*|wdt:P452) ?type.
      VALUES ?type {{ wd:Q4830453 wd:Q783794 wd:Q13235160 }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,lt". }}
    }} LIMIT 60"""
    url = WIKIDATA + "?" + urlencode({"query": query, "format": "json"})
    result = _read_json(url, timeout=18)
    for binding in result.get("results", {}).get("bindings", []):
        site = binding.get("website", {}).get("value")
        name = binding.get("itemLabel", {}).get("value")
        source = binding.get("item", {}).get("value")
        if site and name and source and source.startswith("http"):
            yield site, name, source


def find_websites(country):
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("discovery_country must be a two-letter uppercase country code")
    seen = set()
    errors = []
    for provider in (_osm, _wikidata):
        try:
            for site, name, source in provider(country):
                if site in seen:
                    continue
                seen.add(site)
                yield site, name, source
                if len(seen) >= 40:
                    return
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            errors.append(f"{provider.__name__}: {type(exc).__name__}: {str(exc)[:140]}")
    if not seen:
        raise RuntimeError("Discovery providers unavailable or returned no matching companies: " + " | ".join(errors))
