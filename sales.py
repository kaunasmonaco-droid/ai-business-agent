"""Qualify Apify results, reuse CRM companies by domain, and build unsent drafts."""

import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def company_domain(url):
    return (urlsplit(url).hostname or "").lower().rstrip(".").removeprefix("www.")


def hubspot_request(token, path, payload):
    request = Request(
        "https://api.hubapi.com/crm/v3/objects/companies" + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def sync_company(token, domain, name):
    result = hubspot_request(token, "/search", {
        "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "EQ", "value": candidate}]}
                         for candidate in (domain, "www." + domain)],
        "properties": ["name", "domain"],
        "limit": 2,
    })
    matches = result["results"]
    if len(matches) > 1:
        raise ValueError(f"Multiple HubSpot companies match {domain}")
    if matches:
        return matches[0]["id"], "existing"
    result = hubspot_request(token, "", {"properties": {"name": name, "domain": domain}})
    return result["id"], "created"


def build_drafts(records, token=None, only_domain=None):
    drafts = []
    seen = set()
    for record in records:
        if record.get("status") != "ok" or not record.get("keyword_matches"):
            continue
        source = record["source_url"]
        domain = company_domain(source)
        if not domain or domain in seen or (only_domain and domain != only_domain):
            continue
        email = next((address for address in record.get("generic_contact_emails", [])
                      if address.lower().endswith("@" + domain)), None)
        evidence = (record.get("description") or record.get("title") or "").strip()
        if not email or not evidence:
            continue
        seen.add(domain)
        name = record.get("company_name") or domain.split(".")[0].replace("-", " ").title()
        company_id, crm_status = sync_company(token, domain, name) if token else (None, "preview")
        topics = ", ".join(dict.fromkeys(record["keyword_matches"]))
        drafts.append({
            "company": name,
            "domain": domain,
            "hubspot_company_id": company_id,
            "hubspot_status": crm_status,
            "source_url": source,
            "source_evidence": re.sub(r"\s+", " ", evidence)[:500],
            "recipient": email,
            "subject": f"Potencialių {name} verslo klientų atranka Vokietijoje",
            "body": (
                f"Sveiki, {name} komanda,\n\n"
                f"Peržiūrėjau jūsų viešą įmonės informaciją. Pagal joje rastas temas ({topics}) "
                "siūlau aptarti, kurioms jūsų paslaugoms verta ieškoti naujų užsakovų Vokietijoje. "
                "Galiu parengti 10 potencialių įmonių sąrašą su viešais verslo kontaktais, "
                "šaltiniais ir atrankos pagrindimu.\n\n"
                "Ar Vokietija dabar aktuali? Kurią jūsų paslaugą reikėtų įtraukti pirmiausia?\n\nJulius"
            ),
            "status": "draft",
        })
    return drafts
