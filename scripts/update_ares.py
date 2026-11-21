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
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en,fr;q=0.8"}
PARIS = ZoneInfo("Europe/Paris")
# (page next-fight, nom affiché, diffuseurs en France, tier)
ORGS = [("ares-fc", "Ares FC", ["CANAL+ Sport 360"], "star"), ("pfl", "PFL", ["RMC Sport"], "important")]

import time
def get(url):
    for k in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8", "replace")
        except Exception as e:
            if k == 2: raise
            print("nouvel essai", url, e); time.sleep(10 * (k + 1))

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

METHODS = {"DEC": "Decision", "SUB": "Submission", "TKO": "TKO", "KO": "KO", "DQ": "Disqualification", "NC": "No contest"}

def card_results(page, ev, date, org):
    """Carte complète : chaque combat est un <details class="nf-fight-fold">, le vainqueur porte nf-fight-win."""
    out = []
    for chunk in page.split('<details class="nf-fight-fold"')[1:]:
        chunk = chunk.split("</summary>")[0]
        sides = chunk.split('class="nf-fight-side')
        if len(sides) < 3:
            continue
        names = [re.search(r'class="nf-fight-full">([^<]+)<', x) for x in sides[1:3]]
        pill = re.search(r'class="nf-fight-pill">([^<]+)(?:<span class="nf-fight-detail"><span aria-hidden="true"> · </span>([^<]+))?', chunk)
        if not all(names) or not pill:
            continue  # combat pas encore terminé (ou annulé)
        a, b = (H.unescape(n.group(1)).strip() for n in names)
        txt, det = pill.group(1).strip(), (pill.group(2) or "").strip()
        wa, wb = "nf-fight-win" in sides[1], "nf-fight-win" in sides[2]
        if wa == wb and not re.search(r"draw|nul|nc", txt + " " + det, re.I):
            continue
        rd = re.search(r"R(\d+)", txt)
        m = METHODS.get(txt.split()[0].upper(), txt.split()[0]) if txt else ""
        out.append({"sport": "mma", "org": org, "event": ev.get("name") or "", "date": date, "a": a, "b": b,
                    "w": "a" if wa and not wb else "b" if wb and not wa else "draw",
                    "method": m + (" (" + det.capitalize() + ")" if det else ""), "round": rd.group(1) if rd else None,
                    "time": None, "title": None, "src": "next-fight"})
    return out

def results_of(page, ev, date, org):
    card = card_results(page, ev, date, org)
    key = lambda r: "|".join(sorted(re.sub(r"\W+", "", x.lower())[-6:] for x in (r["a"], r["b"])))
    seen = {key(r) for r in card}
    return card + [r for r in summary_results(page, ev, date, org) if key(r) not in seen]

def summary_results(page, ev, date, org):
    out = []
    m = re.search(r"Top fight results:(.*?)</ul>", page, re.S)
    for li in re.findall(r"<li>(.*?)</li>", m.group(1) if m else "", re.S):
        t = re.sub(r"\s+", " ", text(li)).rstrip(".")
        d = re.match(r"(.+?) defeated (.+?)(?: by (.+?))?(?: in round (\d+))?$", t)
        n = re.match(r"(.+?) and (.+?) fought to a (?:draw|no contest)", t)
        if d:
            out.append({"sport": "mma", "org": org, "event": ev.get("name") or "", "date": date, "a": d.group(1), "b": d.group(2),
                        "w": "a", "method": d.group(3) or "", "round": d.group(4), "time": None, "title": None, "src": "next-fight"})
        elif n:
            out.append({"sport": "mma", "org": org, "event": ev.get("name") or "", "date": date, "a": n.group(1), "b": n.group(2),
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

def scan(slug, name, tv, tier, today):
    org = get(BASE + "/en/organization/" + slug)
    links = sorted(set(re.findall(r'href="(/en/event/[^"#?]+)"', org)))
    rows, res = [], []
    for l in links:
        try:
            time.sleep(2); page = get(BASE + l); ev = jsonld(page)
        except Exception as e:
            print("échec", l, e); continue
        if not ev or not ev.get("startDate"):
            continue
        raw = datetime.datetime.fromisoformat(ev["startDate"].replace("Z", "+00:00"))
        unknown_time = raw.hour == 0 and raw.minute == 0  # minuit UTC = heure non communiquée
        start = raw.astimezone(PARIS) if not unknown_time else raw.replace(tzinfo=PARIS)
        r = results_of(page, ev, start.date().isoformat(), name) if today - datetime.timedelta(days=125) <= start.date() <= today else []
        res += r
        comp = [c.get("name", "").strip() for c in ev.get("competitor", []) if c.get("name")]
        if r or start.date() < today or len(comp) < 2:
            continue  # terminé, passé, ou affiche pas encore connue
        loc = ev.get("location", {}) or {}
        place = ", ".join(x for x in [loc.get("name"), (loc.get("address") or {}).get("addressLocality")] if x)
        rows.append({
            "id": "auto-" + l.rsplit("/", 1)[-1], "sport": "mma", "organization": name,
            "event_name": ev.get("name"), "event_date": start.date().isoformat(),
            "start_time_paris": None if unknown_time else start.strftime("%H:%M"), "location": place or None,
            "fighter_a": comp[0], "fighter_b": comp[1], "weight_class": None, "title": None,
            "card_position": "main", "french_involved": False, "hype_score": 80 if tier == "star" else 65,
            "hype_reason": "Combat principal d'un événement " + name + ".", "tier": tier,
            "broadcasters": tv, "last_seen_at": None,
        })
    return rows, res

def main():
    n = news()
    if n:
        write("auto-news.json", n)
    today = datetime.datetime.now(PARIS).date()
    rows, res, ok = [], [], 0
    for slug, name, tv, tier in ORGS:
        try:
            a, b = scan(slug, name, tv, tier, today); rows += a; res += b; ok += 1
            print(name, ":", len(a), "à venir,", len(b), "résultat(s)")
        except Exception as e:
            print(name, ": next-fight injoignable", e)
    if ok < len(ORGS):
        print("Une organisation a échoué : combats/résultats laissés inchangés,", len(n), "actu(s)"); return
    rows.sort(key=lambda r: r["event_date"]); write("auto-fights.json", rows)
    res.sort(key=lambda r: r["date"], reverse=True); write("auto-results.json", res)
    print(len(rows), "combat(s),", len(res), "résultat(s),", len(n), "actu(s)")

main()
