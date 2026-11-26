"""Discover company websites from public OSM and Wikidata records.

No fabricated leads. Each candidate carries a public source URL.
"""
from html.parser import HTMLParser
import json
import sys
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
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
out tags 100;"""
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
    }} LIMIT 100"""
    url = WIKIDATA + "?" + urlencode({"query": query, "format": "json"})
    result = _read_json(url, timeout=18)
    for binding in result.get("results", {}).get("bindings", []):
        site = binding.get("website", {}).get("value")
        name = binding.get("itemLabel", {}).get("value")
        source = binding.get("item", {}).get("value")
        if site and name and source and source.startswith("http"):
            yield site, name, source



def _search_rss(country, custom_queries=None, custom_keywords=None):
    """Discover candidate websites from a public search RSS feed.

    Search results are leads only; main.py downloads and checks each website
    before accepting it. Search engine pages and directory URLs are excluded.
    """
    terms = {
        "LT": ("metalo apdirbimo paslaugos gamintojas site:.lt", "metalo konstrukcijų gamyba įmonė site:.lt",
               "CNC frezavimas tekinimas gaminame site:.lt", "metal fabrication CNC machining Lithuania", "lakštinio metalo apdirbimas lazerinis pjovimas Lietuva", "steel aluminium manufacturing Lithuania"),
        "UA": ("металообробка виробники Україна", "виробництво металоконструкцій Україна", "metal fabrication manufacturers Ukraine"),
        "DE": ("Metallverarbeitung Hersteller Deutschland", "Blechbearbeitung Hersteller Deutschland"),
        "PL": ("obróbka metali producent Polska", "konstrukcje stalowe producent Polska"),
    }.get(country, (f"metal fabrication manufacturers {country}",))
    if custom_queries:
        terms = tuple(custom_queries[:6])
    excluded = ("thomasnet.com", "cnccookbook.com", "medium.com", "substack.com", "reddit.com", "imf.org", "worldbank.org", "un.org", "gov", "edu", "pdf", "bing.com", "google.com", "facebook.com", "linkedin.com",
                "youtube.com", "wikipedia.org", "rekvizitai.lt", "imones.lt")
    relevant = ("metal", "metalo", "metall", "steel", "plien", "cnc", "fabricat", "gamyb", "lankst", "suvirin", "obrób", "stalow", "blech")
    if custom_keywords:
        relevant = tuple(word.casefold() for word in custom_keywords)
    errors = []
    for term in terms:
        url = "https://www.bing.com/search?" + urlencode({"q": term, "format": "rss", "count": "20"})
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Business-OS/0.6)",
                                            "Accept": "application/rss+xml, application/xml, text/xml"})
            with urlopen(request, timeout=12) as response:
                raw = response.read(500_001)
            if len(raw) > 500_000:
                raise ValueError("Oversized RSS feed")
            root = ET.fromstring(raw)
            for item in root.findall(".//item"):
                link = (item.findtext("link") or "").strip()
                title = (item.findtext("title") or "").strip()
                description = (item.findtext("description") or "").casefold()
                host = (urlsplit(link).hostname or "").lower()
                path = urlsplit(link).path.lower()
                if any(part in path for part in ("/blog/", "/article/", "/articles/", "/news/",
                                                 "/what-is-", "/wiki/", "/guide/", "/tutorial/")):
                    continue
                if (link.startswith(("http://", "https://")) and title and host and
                        not urlsplit(link).path.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx")) and
                        any(word in title.casefold() or word in host or word in description for word in relevant) and
                        not any(host == d or host.endswith("." + d) for d in excluded)):
                    yield link, title[:160], url
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, ET.ParseError) as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:70]}")
    if errors and len(errors) == len(terms):
        raise RuntimeError("RSS searches failed: " + " | ".join(errors))

class MemberDirectory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.member = None
        self.entries = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article":
            self.member = {"name": "", "site": "", "parts": []}
        elif tag == "a" and self.member is not None and "grid-image" in attrs.get("class", "").split():
            self.member.update(site=attrs.get("href", ""), name=attrs.get("title", ""))

    def handle_data(self, text):
        if self.member is not None:
            self.member["parts"].append(text)

    def handle_endtag(self, tag):
        if tag == "article" and self.member is not None:
            member = self.member
            self.member = None
            description = " ".join(member["parts"]).casefold()
            if member["name"] and member["site"].startswith(("http://", "https://")) and any(
                term in description for term in ("cnc", "metalo apdirb", "metalo gamin", "metalo konstrukc", "lakštinio metalo")
            ):
                self.entries.append((member["site"], member["name"]))


def _linpra(country):
    if country != "LT":
        return
    source = "https://linpra.lt/nariu-sarasas/"
    with urlopen(Request(source, headers={"User-Agent": AGENT}), timeout=15) as response:
        page = response.read(2_000_001)
    if len(page) > 2_000_000:
        raise ValueError("Member directory too large")
    parser = MemberDirectory()
    parser.feed(page.decode("utf-8", errors="replace"))
    for site, name in parser.entries:
        yield site, name, source


def find_websites(country, custom_queries=None, custom_keywords=None):
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("discovery_country must be a two-letter uppercase country code")
    seen = set()
    errors = []
    providers = (lambda c: _search_rss(c, custom_queries, custom_keywords),) + (_wikidata,) if custom_queries else (_linpra, _search_rss, _osm, _wikidata)
    for provider in providers:
        try:
            for site, name, source in provider(country):
                if site in seen:
                    continue
                seen.add(site)
                yield site, name, source
                if len(seen) >= 100:
                    return
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            errors.append(f"{provider.__name__}: {type(exc).__name__}: {str(exc)[:140]}")
            print(errors[-1], file=sys.stderr)
    # No candidates is a valid outcome when public providers time out or return
    # nothing. Let the caller emit a transparent no_qualified_companies record
    # rather than failing the entire Actor run.
    if not seen:
        print("Discovery returned zero candidates; provider errors: " + str(len(errors)), file=sys.stderr)
        return
