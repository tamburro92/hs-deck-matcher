import json, re, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import cards as cardmod, store

STATE = {"msg": "", "busy": False, "error": None}
LOCK = threading.Lock()
TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "index.html"


def build_data() -> dict:
    meta_f, coll_f = Path("data/meta.json"), Path("data/collection.json")
    if not meta_f.exists():
        return {"empty": True}
    meta = json.loads(meta_f.read_text())
    arch = {}
    try:
        arch = {a["id"]: a["name"] for a in json.loads(Path("data/archetypes.json").read_text())}
    except Exception:
        pass
    allcards = cardmod.load_cards()
    decks, used = [], {}
    for cls, lst in meta["series"]["data"].items():
        for d in lst:
            cl = json.loads(d["deck_list"])
            if any(i not in allcards for i, _ in cl):
                continue
            for i, _ in cl:
                used[i] = cardmod.card_info(allcards[i])
            decks.append({"id": d["deck_id"], "cls": cls, "name": arch.get(d["archetype_id"]) or f"{cls.title()} (altro)",
                          "games": d["total_games"], "wr": d["win_rate"], "cards": cl,
                          "code": cardmod.deckstring(cls, cl)})
    store.save(meta["as_of"], decks)
    win = store.windows(decks)
    for d in decks:
        d["w"] = win.get(d["id"], {})
    coll = None
    if coll_f.exists():
        accs = json.loads(coll_f.read_text())
        acc = max(accs.values(), key=lambda a: len(a.get("collection", {})), default=None)
        if acc:
            coll = {"cards": {k: sum(v) for k, v in acc["collection"].items()}, "dust": acc.get("dust", 0)}
    guru = None
    gf = Path("data/guru.json")
    if gf.exists():
        guru = json.loads(gf.read_text())
        for d in guru["decks"]:
            for i, _ in d["cards"]:
                used[i] = cardmod.card_info(allcards[i])
    return {"as_of": meta["as_of"], "rank": "Bronze–Gold", "decks": decks, "cards": used, "collection": coll, "guru": guru}


SNIPPET = r"""(async()=>{const g=async u=>{const r=await fetch(u,{credentials:'include'});if(!r.ok)throw new Error(u+' '+r.status);return r.json()};
try{const meta=await g('/analytics/query/list_decks_by_win_rate_v2/?GameType=RANKED_STANDARD&LeagueRankRange=BRONZE_THROUGH_GOLD&Region=ALL&TimeRange=CURRENT_PATCH');
let arch=[];try{arch=await g('/api/v1/archetypes/')}catch(e){}
const col={};try{const acc=await g('/api/v1/account/');for(const b of acc.blizzard_accounts||[]){for(const base of ['/api/v1/collection/','https://api.hsreplay.net/v1/collection/']){try{col[b.account_hi+'_'+b.account_lo]=await g(base+'?account_hi='+b.account_hi+'&account_lo='+b.account_lo+'&format=json');break}catch(e){}}}}catch(e){console.warn('collezione:',e.message)}
const r=await fetch('http://127.0.0.1:PORT/api/ingest',{method:'POST',body:JSON.stringify({meta,arch,col})});
console.log(r.ok?'HS Deck Matcher: dati inviati ('+Object.keys(col).length+' account con collezione). Torna alla scheda dell\'app.':'Errore app '+r.status)}catch(e){console.error('HS Deck Matcher:',e.message)}})();"""
GURU_SNIPPET = r"""(async()=>{try{
const rows=[],seen=new Set();
for(const c of document.querySelectorAll('.card')){
 const btn=c.querySelector('[data-clipboard-text]');if(!btn)continue;
 const m=(btn.getAttribute('data-clipboard-text')||'').match(/AAE[A-Za-z0-9+\/=]{30,}/);if(!m||seen.has(m[0]))continue;seen.add(m[0]);
 const a=c.querySelector('.deck-title a');
 const tags=[...c.querySelectorAll('.columns .tag')];
 const wr=parseFloat((tags[0]&&tags[0].innerText||'').replace(',','.'));
 const g=((c.querySelector('.columns')||{}).innerText||'').match(/Games:\s*([\d.,]+)/);
 rows.push({code:m[0],name:a?a.textContent.trim():'',url:a?a.href:'',wr:isNaN(wr)?null:wr,games:g?parseInt(g[1].replace(/[.,]/g,''),10):null})}
const r=await fetch('http://127.0.0.1:PORT/api/ingest_guru',{method:'POST',body:JSON.stringify({url:location.href,rows})});
console.log(r.ok?'HS Deck Matcher: '+rows.length+' deck inviati da HSGuru. Torna alla scheda dell\'app.':'Errore app '+r.status)}catch(e){console.error('HS Deck Matcher:',e.message)}})();"""
PORT = 8765


_NUM = re.compile(r"\d[\d.,]*")


def _name(text: str) -> str:
    words = []
    for w in text.replace("#", " ").split():
        if re.search(r"\d|%", w) or len(words) >= 4:
            break
        words.append(w)
    return " ".join(words)


def parse_guru(body: dict) -> dict:
    """Decodifica i deck code trovati nella pagina HSGuru; winrate/partite dal testo della riga."""
    from hearthstone.deckstrings import Deck
    allcards = cardmod.load_cards()
    inv = {v: k for k, v in cardmod.HEROES.items()}
    decks, bad = [], 0
    for r in body.get("rows", []):
        try:
            d = Deck.from_deckstring(r["code"])
            cl = [[int(i), int(n)] for i, n in d.cards]
            if any(i not in allcards for i, _ in cl) or sum(n for _, n in cl) != 30:
                raise ValueError
            cls = inv.get(d.heroes[0]) or (allcards[d.heroes[0]].get("cardClass") if d.heroes[0] in allcards else None)
            if cls not in cardmod.HEROES:
                raise ValueError
        except Exception:
            bad += 1
            continue
        text = (r.get("text") or "").replace(r["code"], " ")
        text = re.sub(r"\s+", " ", text).strip()
        pct = [float(x) for x in re.findall(r"(\d{1,3}(?:[.,]\d+)?)\s*%", text.replace(",", "."))]
        wr = r.get("wr") if r.get("wr") is not None else next((x for x in pct if 20 <= x <= 90), None)
        nums = [int(n.replace(",", "").replace(".", "")) for n in _NUM.findall(re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", text)) if n.strip(",.")]
        games = r.get("games") if r.get("games") is not None else max([n for n in nums if n >= 30] or [0])
        decks.append({"id": r["code"], "cls": cls, "name": (r.get("name") or "").lstrip("# ").strip() or _name(text) or cls.title(),
                      "games": games, "wr": wr if wr is not None else 0, "cards": cl, "code": r["code"],
                      "w": {}, "raw": text})
    return {"decks": decks, "url": body.get("url"), "bad": bad, "n": len(body.get("rows", []))}


def ingest_guru(body: dict):
    Path("data").mkdir(exist_ok=True)
    out = parse_guru(body)
    out["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    Path("data/guru.json").write_text(json.dumps(out))
    STATE["msg"] = "Dati ricevuti"


def ingest(body: dict):
    Path("data").mkdir(exist_ok=True)
    Path("data/meta.json").write_text(json.dumps(body["meta"]))
    Path("data/archetypes.json").write_text(json.dumps(body.get("arch") or []))
    if body.get("col"):
        Path("data/collection.json").write_text(json.dumps(body["col"]))
    STATE["msg"] = "Dati ricevuti"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body: bytes, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(TEMPLATE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/data":
            self._send(json.dumps(build_data()).encode())
        elif self.path == "/api/snippet":
            STATE["msg"] = ""
            self._send(SNIPPET.replace("PORT", str(PORT)).encode(), "text/plain; charset=utf-8")
        elif self.path == "/api/snippet_guru":
            STATE["msg"] = ""
            self._send(GURU_SNIPPET.replace("PORT", str(PORT)).encode(), "text/plain; charset=utf-8")
        elif self.path == "/api/status":
            self._send(json.dumps(STATE).encode())
        else:
            self._send(b"{}", code=404)

    def _cors(self):
        o = self.headers.get("Origin", "")
        self.send_header("Access-Control-Allow-Origin", o if o.endswith(("hsreplay.net", "hsguru.com")) else "https://hsreplay.net")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path in ("/api/ingest", "/api/ingest_guru"):
            n = int(self.headers.get("Content-Length", 0))
            try:
                (ingest_guru if self.path.endswith("guru") else ingest)(json.loads(self.rfile.read(n)))
                body, code = b'{"ok":true}', 200
            except Exception as e:
                STATE["error"] = str(e)
                body, code = b'{"ok":false}', 400
            self.send_response(code)
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(b"{}", code=404)


def serve(port=PORT, open_browser=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{port}/"
    print("HS Deck Matcher su", url, "(Ctrl+C per uscire)")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
