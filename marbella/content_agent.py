"""Zero-cost draft-only content planner for Elite Marbella Cars.
No publishing, messaging, scraping, subscriptions, or paid APIs.
"""
import argparse
import datetime
import json
from pathlib import Path

FORMATS = [
    ("Reel", "Marbella arrival", "Your Marbella arrival deserves a memorable drive."),
    ("Story", "SUV or convertible?", "Which would you choose for the Costa del Sol?"),
    ("Reel", "Puerto Banus experience", "The destination is Marbella. The experience starts with your drive."),
    ("Story", "Choose your dates", "Planning a Marbella stay? Tell us your dates."),
    ("Reel", "Weekend escape", "Make your Costa del Sol weekend unforgettable."),
    ("Story", "Rental enquiry guide", "Your dates. Your preferred car. We check the options."),
    ("Reel", "Marbella collection", "Luxury driving, carefully matched to your trip."),
]
CTA = "DM 'MARBELLA' with your dates and preferred car for an availability check."

def plan(brief):
    if brief.get("account") != "@elitemarbella_cars":
        raise ValueError("Account must be @elitemarbella_cars")
    date = datetime.date.fromisoformat(brief["start_date"])
    items = []
    for i, (format_, concept, hook) in enumerate(FORMATS):
        items.append({
            "date": str(date + datetime.timedelta(days=i)),
            "account": brief["account"],
            "format": format_,
            "concept": concept,
            "hook": hook,
            "caption_draft": hook + "\n\n" + CTA + "\n\n#Marbella #PuertoBanus #CostaDelSol #LuxuryCarRental",
            "visual_brief": "9:16 real authorized partner car footage; bright Marbella/Puerto Banus setting; smooth fixed/stabilized motion; legible overlays held 4-6 seconds; 15-25 seconds for Reel; use licensed original audio.",
            "availability_claim": "none",
            "price_claim": "none",
            "needs_authorized_real_footage": True,
            "requires_human_approval": True,
            "publication_status": "DRAFT_NOT_PUBLISHED",
            "payment_requested": False,
        })
    return items

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", default="marbella/brief.json")
    parser.add_argument("--output", default="marbella/weekly_content.json")
    args = parser.parse_args()
    with open(args.brief, encoding="utf-8") as src:
        brief = json.load(src)
    result = plan(brief)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print("Generated", len(result), "drafts. NO SOCIAL POSTS WERE PUBLISHED.")

if __name__ == "__main__":
    main()
