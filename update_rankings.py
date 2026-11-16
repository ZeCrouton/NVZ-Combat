"""Récupère les classements UFC (Media + Meta, dont P4P) sur https://lasueur.com/classement-ufc
et écrit data/rankings.json (lu par le site). Aucune clé API nécessaire."""
import json, os, re, sys, datetime, urllib.request
from html.parser import HTMLParser

URL = "https://lasueur.com/classement-ufc"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "rankings.json")
EN = re.compile(r"((?:Women's |Men's )?(?:Pound-for-Pound|Light Heavyweight|Heavyweight|Middleweight|Welterweight|Lightweight|Featherweight|Bantamweight|Flyweight|Strawweight))\s*$", re.I)
ROW = re.compile(r"^(C|\d{1,2})\s+(.+?)(?:\s+(NEW|[↑↓]\s*\d+))?$")

class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.items = []; self.cur = None; self.depth = 0
    def handle_starttag(self, tag, a):
        if self.cur is None and tag in ("h2", "h3", "h4", "h5", "li"):
            self.cur = [tag, []]; self.depth = 1
        elif self.cur is not None and tag == self.cur[0]:
            self.depth += 1
    def handle_endtag(self, tag):
        if self.cur is not None and tag == self.cur[0]:
            self.depth -= 1
            if self.depth == 0:
                self.items.append((self.cur[0], re.sub(r"\s+", " ", " ".join(self.cur[1])).strip())); self.cur = None
    def handle_data(self, d):
        if self.cur is not None and d.strip(): self.cur[1].append(d.strip())

req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (compatible; NVZ-Combat-bot)", "Accept-Language": "fr"})
html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
p = P(); p.feed(html)

boards = {"media": [], "meta": []}; board, div = "media", None
for tag, txt in p.items:
    if tag != "li":
        if re.fullmatch(r"meta ranking", txt, re.I): board, div = "meta", None; continue
        if re.fullmatch(r"media ranking", txt, re.I): board, div = "media", None; continue
        m = EN.search(txt)
        if not m or tag not in ("h3", "h4", "h5"): div = None; continue
        name = m.group(1)
        if board == "media" and any(d["name"] == name for d in boards["media"]): board = "meta"  # 2e série = Meta
        div = {"name": name, "list": []}; boards[board].append(div)
    elif div is not None:
        m = ROW.match(txt)
        if not m: continue
        mv = (m.group(3) or "").replace(" ", "")
        div["list"].append({"rank": 0 if m.group(1) == "C" else int(m.group(1)), "name": m.group(2), "sub": "Nouveau" if mv == "NEW" else mv.replace("↑", "▲ ").replace("↓", "▼ ")})
for k in boards: boards[k] = [d for d in boards[k] if len(d["list"]) >= 10]
if len(boards["media"]) < 8:
    print("Parsing échoué : structure de la page modifiée ?", {k: len(v) for k, v in boards.items()}, file=sys.stderr); sys.exit(1)
src = re.search(r"actualis\w+ le (\d{1,2} \w+ \d{4})", re.sub(r"<[^>]+>", " ", html))
new = {"updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "src": src.group(1) if src else None, "media": boards["media"], "meta": boards["meta"]}
try: cur = json.load(open(OUT, encoding="utf-8"))
except Exception: cur = {}
if (new["media"], new["meta"]) == (cur.get("media"), cur.get("meta")): print("Aucun changement"); sys.exit(0)
json.dump(new, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Classements mis à jour :", {k: len(v) for k, v in boards.items()})
