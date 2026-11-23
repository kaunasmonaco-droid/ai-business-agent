# ELITE MARBELLA CARS – draft-only content agent

An autonomous, **zero-paid-API** Instagram content preparation module, separate from the supplier profiler. Outputs seven complete English caption drafts and short video/story creative briefs for `@elitemarbella_cars`.

Run: `python marbella/content_agent.py --brief marbella/brief.json --output marbella/weekly_content.json`.

- **Never posts, DMs, comments, pays, buys ads, claims confirmed car inventory, or schedules publication.**
- Posts/Reels/Stories are only publishable through an authorized Instagram connector (currently the user's connected Windsor.ai), after actual media accessibility verification and user approval for specific creative assets.
- No guaranteed availability, prices, or commissions. Only approved partner car footage.
- No claims about actual new enquiries without platform evidence.
- Source for user-approved campaign schedule is in AI BUSINESS OS MARBELLA OPS Google Sheet.
- Google Actions workflow validates drafts, builds an artifact; its plan-limited runner minutes are not unlimited.
