"""Robot NVZ Combat (GitHub Actions), sans clé API :
- data/auto-fights.json  : prochains événements Ares FC (combat principal), JSON-LD de next-fight.com
- data/auto-results.json : résultats Ares FC des 4 derniers mois (résumé « Top fight results » de next-fight.com)
- data/auto-news.json    : actus Google Actualités (MMA, boxe, Ares), lues par le site sans proxy"""
import json, os, re, sys, html as H, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

BASE = "https://next-fight.com"
DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "auto-fights.json")
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

def text(x):
    return H.unescape(re.sub(r"<[^>]+>", "", x)).strip()

def results_of(page, ev, date):
    out = []
    m = re.search(r"Top fight results:(.*?)</ul>", page, re.S)
    for li in re.findall(r"<li>(.*?)</li>", m.group(1) if m else "", re.S):
        t = re.sub(r"\s+", " ", text(li)).rstrip(".")
        d = re.match(r"(.+?) defeated (.+?)(?: by (.+?))?(?: in round (\d+))?$", t)
        n = re.match(r"(.+?) and (.+?) fought to a (?:draw|no contest)", t)
        if d:
            out.append({"sport": "mma", "org": "Ares FC", "event": ev.get("name") or "", "date": date, "a": d.group(1), "b": d.group(2),
                        "w": "a", "method": d.group(3) or "", "round": d.group(4), "time": None, "title": None, "src": "next-fight"})
        elif n:
            out.append({"sport": "mma", "org": "Ares FC", "event": ev.get("name") or "", "date": date, "a": n.group(1), "b": n.group(2),
                        "w": "draw", "method": "", "round": None, "time": None, "title": None, "src": "next-fight"})
    return out

G = "https://news.google.com/rss/search?hl=fr&gl=FR&ceid=FR:fr&q="
FEEDS = [("MMA UFC", "mma"), ("boxe championnat du monde", "boxe"), ("PFL OR KSW OR Hexagone MMA", "mma"), ('"Ares" MMA', "mma")]

def news():
    out, seen = [], set()
    for q, sp in FEEDS:
        try:
            root = ET.fromstring(get(G + urllib.parse.quote(q)))
        except Exception as e:
            print("flux en échec", q, e); continue
        for it in root.iter("item"):
            t, l, d = it.findtext("title") or "", it.findtext("link") or "", it.findtext("pubDate") or ""
            src = it.findtext("source") or "Google Actus"
            t = re.sub(r" - [^-]+$", "", t).strip()
            k = re.sub(r"\W+", "", t.lower())[:60]
            if not t or not l or not d or k in seen:
                continue
            seen.add(k)
            try:
                ms = int(parsedate_to_datetime(d).timestamp() * 1000)
            except Exception:
                continue
            out.append({"t": t, "l": l, "d": ms, "s": src, "sp": sp, "lg": "fr"})
    out.sort(key=lambda n: -n["d"])
    return out[:150]

def write(name, rows):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2); f.write("\n")

def main():
    org = get(BASE + "/en/organization/ares-fc")
    links = sorted(set(re.findall(r'href="(/en/event/[^"#?]+)"', org)))
    today = datetime.datetime.now(PARIS).date()
    rows, res = [], []
    for l in links:
        try:
            page = get(BASE + l); ev = jsonld(page)
        except Exception as e:
            print("échec", l, e); continue
        if not ev:
            continue
        if ev.get("startDate"):
            d0 = datetime.datetime.fromisoformat(ev["startDate"].replace("Z", "+00:00")).astimezone(PARIS).date()
            if today - datetime.timedelta(days=125) <= d0 <= today:
                res += results_of(page, ev, d0.isoformat())
        comp = [c.get("name", "").strip() for c in ev.get("competitor", []) if c.get("name")]
        if len(comp) < 2 or not ev.get("startDate"):
            continue  # affiche pas encore connue (« tbd vs tbd »)
        raw = datetime.datetime.fromisoformat(ev["startDate"].replace("Z", "+00:00"))
        unknown_time = raw.hour == 0 and raw.minute == 0  # minuit UTC = heure non communiquée
        start = raw.astimezone(PARIS) if not unknown_time else raw.replace(tzinfo=PARIS)
        if start.date() < today or any(r["event"] == ev.get("name") for r in res):  # terminé = plus « à venir »
            continue
        loc = ev.get("location", {}) or {}
        place = ", ".join(x for x in [loc.get("name"), (loc.get("address") or {}).get("addressLocality")] if x)
        rows.append({
            "id": "auto-" + l.rsplit("/", 1)[-1], "sport": "mma", "organization": "Ares FC",
            "event_name": ev.get("name"), "event_date": start.date().isoformat(),
            "start_time_paris": None if unknown_time else start.strftime("%H:%M"), "location": place or None,
            "fighter_a": comp[0], "fighter_b": comp[1], "weight_class": None, "title": None,
            "card_position": "main", "french_involved": False, "hype_score": 80,
            "hype_reason": "Combat principal d'un événement Ares FC.", "tier": "star",
            "broadcasters": [], "last_seen_at": None,
        })
    if not rows and not links:
        print("Aucun lien d'événement trouvé : fichier laissé inchangé"); sys.exit(1)
    rows.sort(key=lambda r: r["event_date"])
    write("auto-fights.json", rows)
    if links:
        res.sort(key=lambda r: r["date"], reverse=True); write("auto-results.json", res)
    n = news()
    if n:
        write("auto-news.json", n)
    print(len(rows), "combat(s) Ares,", len(res), "résultat(s),", len(n), "actu(s)")

main()
