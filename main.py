"""AI BUSINESS OS – Source-verified company website profiler. No paid APIs."""
import argparse
import csv
import io
import http.client
import ssl
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from discovery import find_websites
from sales import build_drafts, company_domain

MAX_SITES = 10
MAX_BYTES = 1_200_000
USER_AGENT = "AIBusinessOS-CompanyResearch/0.1 (+public-source-verification)"
GENERIC_PREFIXES = ("info", "hello", "contact", "sales", "export", "office", "enquiries", "inquiries", "support")

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._in_title = False
        self._ignored = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._ignored += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key in ("description", "og:description") and not self.description:
                self.description = attrs.get("content", "")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self._ignored = max(0, self._ignored - 1)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._ignored:
            return
        s = re.sub(r"\s+", " ", data).strip()
        if s:
            if self._in_title:
                self.title += (" " if self.title else "") + s
            else:
                self.parts.append(s)

def validate_public_url(value):
    """Limit to HTTPS public hostnames; reject direct IP and local/reserved DNS."""
    if not isinstance(value, str):
        raise ValueError("URL must be a string")
    p = urllib.parse.urlsplit(value.strip())
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Only HTTPS public hostname URLs are allowed")
    host = p.hostname.lower().rstrip(".")
    if (host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test"))
            or "." not in host):
        raise ValueError("Local hostname rejected")
    try:
        ipaddress.ip_address(host)
        raise ValueError("Direct IP URLs are not supported")
    except ValueError as exc:
        if str(exc) == "Direct IP URLs are not supported":
            raise
    return p.geturl()

def public_dns(host):
    """Reject private, reserved or local destinations after DNS resolution."""
    records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ips = {record[4][0] for record in records}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("Target resolved to a non-public address")
    return sorted(ips)

class PublicHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        addresses = public_dns(self.host)
        error = None
        for address in addresses:
            try:
                raw = socket.create_connection((address, self.port), self.timeout)
                try:
                    self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                except BaseException:
                    raw.close()
                    raise
                return
            except OSError as exc:
                error = exc
        raise error


def download_page(url):
    for _ in range(3):
        url = validate_public_url(url)
        parsed = urllib.parse.urlsplit(url)
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection = PublicHTTPSConnection(parsed.hostname, timeout=9, context=ssl.create_default_context())
        try:
            connection.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
            with connection.getresponse() as response:
                if response.status in (301, 302, 303, 307, 308) and response.getheader("Location"):
                    url = urllib.parse.urljoin(url, response.getheader("Location"))
                    continue
                if not 200 <= response.status < 300:
                    raise ValueError(f"Website returned HTTP {response.status}")
                content_type = (response.getheader("Content-Type") or "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    raise ValueError("Not an HTML page")
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("Page too large")
                return url, data.decode("utf-8", errors="replace")
        finally:
            connection.close()
    raise ValueError("Too many redirects")


def profile_one(url, keywords=None, fetcher=download_page):
    validated_url = validate_public_url(url)
    final_url, html = fetcher(validated_url)
    parser = TextParser()
    parser.feed(html)
    body = re.sub(r"\s+", " ", " ".join(parser.parts))[:7000]
    words = [str(x).strip().lower() for x in (keywords or []) if str(x).strip()][:10]
    matches = [word for word in words if word in body.lower()]
    emails = re.findall(r"(?i)(?<![\w.+-])([\w.+-]+@[\w.-]+\.[a-z]{2,})(?![\w.-])", html)
    generic = sorted({e.lower() for e in emails if e.split("@")[0].lower() in GENERIC_PREFIXES})[:5]
    return {
        "source_url": final_url,
        "title": parser.title[:180] or None,
        "description": parser.description[:500] or None,
        "public_evidence_excerpt": body[:550] or None,
        "keyword_matches": matches,
        "keyword_match_count": len(matches),
        "generic_contact_emails": generic,
        "verified_buyer_interest": False,
        "verification_note": "Public website data only. No verification of purchasing intent or order availability.",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }

def _metal_manufacturer(record):
    """Require specific production evidence, not generic words such as 'gamyba'."""
    text = " ".join(str(record.get(k) or "") for k in
                    ("title", "description", "public_evidence_excerpt")).lower()
    negatives = ("kolegija", "college", "university", "universitet", "academy",
                 "akademija", "supermarket", "grocery", "prekybos tinklas",
                 "bank", "ministerija", "municipality", "school")
    if any(term in text for term in negatives):
        return False
    phrases = ("metalo apdirb", "metalo konstrukc", "metalo gamyb",
               "metalo lankst", "metalo pjov", "metalo suvirin",
               "lakštinio metalo", "cnc machining", "metal fabrication",
               "metalworking", "sheet metal", "steel fabrication",
               "metallbearbeitung", "blechbearbeitung", "obróbka metali")
    return any(term in text for term in phrases)


def run(payload, fetcher=download_page):
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object")
    urls = payload.get("urls", [])
    country = payload.get("discovery_country")
    if country and urls:
        raise ValueError("Choose discovery_country or supplied urls, not both")
    keywords = payload.get("keywords", [])
    if not isinstance(keywords, list):
        raise ValueError("keywords must be an array")
    output = []
    seen = set()
    if country:
        candidates = find_websites(country)
    else:
        if not isinstance(urls, list) or not 1 <= len(urls) <= MAX_SITES:
            raise ValueError("Provide 1-10 source website URLs")
        candidates = ((url, None, None) for url in urls)
    attempted = 0
    for website, name, source in candidates:
        if country and attempted >= 40:
            break
        try:
            if not isinstance(website, str):
                continue
            if website.startswith("http://"):
                website = "https://" + website[7:]
            website = validate_public_url(website)
            domain = company_domain(website)
            if domain in seen:
                continue
            seen.add(domain)
            attempted += 1
            record = profile_one(website, keywords, fetcher=fetcher)
            if company_domain(record["source_url"]) != domain:
                continue
            if country and not _metal_manufacturer(record):
                continue
            if country:
                record["company_name"] = name
                record["discovery_source_url"] = source
            output.append(record)
        except Exception as exc:
            if not country:
                output.append({"source_url": str(website), "status": "error",
                               "error": str(exc)[:220], "verified_buyer_interest": False})
        if len(output) >= MAX_SITES:
            break
    if country and not output:
        return [{"status": "no_qualified_companies", "country": country,
                 "attempted_sites": attempted,
                 "error": "No verified metal manufacturing websites found in this run",
                 "verified_buyer_interest": False}]
    return output

def apify_get_input():
    store = os.getenv("APIFY_DEFAULT_KEY_VALUE_STORE_ID")
    token = os.getenv("APIFY_TOKEN")
    if not store or not token:
        return None
    key = os.getenv("ACTOR_INPUT_KEY", "INPUT")
    base = os.getenv("APIFY_API_BASE_URL", "https://api.apify.com").rstrip("/")
    url = f"{base}/v2/key-value-stores/{urllib.parse.quote(store)}/records/{urllib.parse.quote(key)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read(1_000_000).decode())

def apify_push(records):
    dataset = os.getenv("APIFY_DEFAULT_DATASET_ID")
    token = os.getenv("APIFY_TOKEN")
    if not dataset or not token:
        return False
    base = os.getenv("APIFY_API_BASE_URL", "https://api.apify.com").rstrip("/")
    endpoint = f"{base}/v2/datasets/{urllib.parse.quote(dataset)}/items"
    data = json.dumps(records, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as res:
        if res.status not in (200, 201, 204):
            raise ValueError(f"Apify dataset write failed: {res.status}")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Local JSON input path, no API token required")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--from-results", help="Replay an existing Apify JSON export")
    parser.add_argument("--drafts", help="Write proposal drafts to this JSON path")
    parser.add_argument("--company-domain", help="Process only this domain in the sales stage")
    parser.add_argument("--sync-hubspot", action="store_true", help="Write to HubSpot using HUBSPOT_ACCESS_TOKEN")
    args = parser.parse_args()
    if args.input and args.from_results:
        parser.error("Choose either --input or --from-results")
    if args.sync_hubspot and not args.drafts:
        parser.error("--sync-hubspot requires --drafts")
    if args.from_results:
        with open(args.from_results, encoding="utf-8") as stream:
            result = json.load(stream)
        if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
            parser.error("Expected a JSON array of Apify result objects")
        write_drafts(result, args.drafts, args.company_domain, args.sync_hubspot)
        return
    actor_mode = not args.input
    if args.input:
        with open(args.input, encoding="utf-8") as stream:
            payload = json.load(stream)
    else:
        payload = apify_get_input()
        if payload is None:
            raise SystemExit("Missing input: use --input example_input.json, or Apify runtime")
    result = run(payload)
    output = json.dumps(result, indent=2, ensure_ascii=False)
    print(output)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(output + "\n")
    if actor_mode:
        apify_push(result)
    if args.drafts:
        write_drafts(result, args.drafts, args.company_domain, args.sync_hubspot)
    elif actor_mode and payload.get("sales_pipeline") is True:
        drafts = write_drafts(result, None, payload.get("company_domain"), True)
        save_apify_drafts(drafts)

def write_drafts(records, path, domain, sync):
    token = os.getenv("HUBSPOT_ACCESS_TOKEN") if sync else None
    if sync and not token:
        raise SystemExit("HUBSPOT_ACCESS_TOKEN is required for CRM writes")
    drafts = build_drafts(records, token, domain)
    if not drafts:
        raise SystemExit("No qualified companies with same-domain public business contacts")
    if path:
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(drafts, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return drafts


def save_apify_drafts(drafts):
    store = os.environ["APIFY_DEFAULT_KEY_VALUE_STORE_ID"]
    token = os.environ["APIFY_TOKEN"]
    base = os.getenv("APIFY_API_BASE_URL", "https://api.apify.com").rstrip("/")
    endpoint = f"{base}/v2/key-value-stores/{urllib.parse.quote(store, safe='')}/records/PROPOSAL_DRAFTS"
    request = urllib.request.Request(
        endpoint, method="PUT", data=json.dumps(drafts, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20):
        pass


if __name__ == "__main__":
    main()
