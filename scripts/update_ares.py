"""Récupère les prochains événements Ares FC (combat principal) sur next-fight.com
et écrit data/auto-fights.json (même format que la base, fusionné par index.html).
Source : JSON-LD schema.org SportsEvent de chaque page événement. Aucune clé API."""
import json, os, re, sys, datetime, urllib.request
from zoneinfo import ZoneInfo

BASE = "https://next-fight.com"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "auto-fights.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; NVZ-Combat-bot)", "Accept-Language": "en"}
PARIS = ZoneInfo("Europe/Paris")

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8", "replace")

def jsonld(html):
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict) and x.get("@type") == "SportsEvent":
                return x
    return None

def main():
    org = get(BASE + "/en/organization/ares-fc")
    links = sorted(set(re.findall(r'href="(/en/event/[^"#?]+)"', org)))
    today = datetime.datetime.now(PARIS).date()
    rows = []
    for l in links:
        try:
            ev = jsonld(get(BASE + l))
        except Exception as e:
            print("échec", l, e); continue
        if not ev:
            continue
        comp = [c.get("name", "").strip() for c in ev.get("competitor", []) if c.get("name")]
        if len(comp) < 2 or not ev.get("startDate"):
            continue  # affiche pas encore connue (« tbd vs tbd »)
        start = datetime.datetime.fromisoformat(ev["startDate"].replace("Z", "+00:00")).astimezone(PARIS)
        if start.date() < today:
            continue
        loc = ev.get("location", {}) or {}
        place = ", ".join(x for x in [loc.get("name"), (loc.get("address") or {}).get("addressLocality")] if x)
        rows.append({
            "id": "auto-" + l.rsplit("/", 1)[-1], "sport": "mma", "organization": "Ares FC",
            "event_name": ev.get("name"), "event_date": start.date().isoformat(),
            "start_time_paris": start.strftime("%H:%M"), "location": place or None,
            "fighter_a": comp[0], "fighter_b": comp[1], "weight_class": None, "title": None,
            "card_position": "main", "french_involved": False, "hype_score": 80,
            "hype_reason": "Combat principal d'un événement Ares FC.", "tier": "star",
            "broadcasters": [], "last_seen_at": None,
        })
    if not rows and not links:
        print("Aucun lien d'événement trouvé : fichier laissé inchangé"); sys.exit(1)
    rows.sort(key=lambda r: r["event_date"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2); f.write("\n")
    print(len(rows), "combat(s) Ares écrit(s)")

main()
