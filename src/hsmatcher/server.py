import hashlib, json, re, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse

from hearthstone.enums import FormatType

from . import cards as cardmod, store

STATE = {"msg": "", "error": None, "last": None}
TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "index.html"
HS_DIR, GURU_DIR = Path("data/hs"), Path("data/guru")
SCHEMA_F = Path("data/guru_schema.json")
PORT = 8765

# Filtri di HSReplay: (valore, etichetta, richiede Premium). LAST_1_DAY / LAST_3_DAYS non esistono per questa query.
HS_OPTIONS = {
    "GameType": [("RANKED_STANDARD", "Standard", False), ("RANKED_WILD", "Wild", False)],
    "LeagueRankRange": [("BRONZE_THROUGH_GOLD", "Bronzo–Oro", False), ("DIAMOND_THROUGH_LEGEND", "Diamante–Leggenda", True),
                        ("LEGEND", "Leggenda", True), ("TOP_1000_LEGEND", "Top 1000 Leggenda", True)],
    "TimeRange": [("CURRENT_PATCH", "Patch corrente", False), ("CURRENT_EXPANSION", "Espansione corrente", False),
                  ("LAST_7_DAYS", "Ultimi 7 giorni", True)],
}
HS_LABEL = {k: {v: l for v, l, _ in o} for k, o in HS_OPTIONS.items()}


def hs_key(p: dict) -> str:
    return f"{p['GameType']}__{p['LeagueRankRange']}__{p['TimeRange']}"


def hs_params(q: dict) -> dict:
    out = {}
    for k in HS_OPTIONS:
        v = q.get(k, "")
        if v not in HS_LABEL[k]:
            raise ValueError(f"parametro non valido: {k}={v}")
        out[k] = v
    return out


def guru_key(url: str) -> str:
    q = sorted((k, v) for k, v in parse_qsl(urlparse(url or "").query) if k != "page" and not k.startswith("_") and v != "")
    return urlencode(q)


def _file_guru(key: str) -> Path:
    return GURU_DIR / (hashlib.sha1(key.encode()).hexdigest()[:10] + ".json")


def migrate():
    """Porta i file della prima versione (meta.json, guru.json) nella struttura a dataset."""
    m = Path("data/meta.json")
    if m.exists():
        HS_DIR.mkdir(parents=True, exist_ok=True)
        p = {"GameType": "RANKED_STANDARD", "LeagueRankRange": "BRONZE_THROUGH_GOLD", "TimeRange": "CURRENT_PATCH"}
        dest = HS_DIR / f"{hs_key(p)}.json"
        if not dest.exists():
            meta = json.loads(m.read_text())
            at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(m.stat().st_mtime))
            dest.write_text(json.dumps({"params": p, "at": at, "meta": meta}))
        m.unlink()
    g = Path("data/guru.json")
    if g.exists():
        d = json.loads(g.read_text())
        d["key"] = guru_key(d.get("url", ""))
        GURU_DIR.mkdir(parents=True, exist_ok=True)
        _file_guru(d["key"]).write_text(json.dumps(d))
        g.unlink()


def _arch() -> dict:
    try:
        return {a["id"]: a["name"] for a in json.loads(Path("data/archetypes.json").read_text())}
    except Exception:
        return {}


def parse_hs(meta: dict, wild: bool) -> tuple[list[dict], dict]:
    allcards, arch = cardmod.load_cards(), _arch()
    fmt = FormatType.FT_WILD if wild else FormatType.FT_STANDARD
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
                          "code": cardmod.deckstring(cls, cl, fmt)})
    return decks, used


def list_hs() -> list[dict]:
    out = []
    for f in HS_DIR.glob("*.json") if HS_DIR.exists() else []:
        d = json.loads(f.read_text())
        p = d["params"]
        out.append({"key": hs_key(p), "params": p, "at": d["at"], "as_of": d["meta"].get("as_of"),
                    "label": " · ".join(HS_LABEL[k][p[k]] for k in HS_OPTIONS)})
    return sorted(out, key=lambda x: x["at"], reverse=True)


def list_guru() -> list[dict]:
    out = []
    for f in GURU_DIR.glob("*.json") if GURU_DIR.exists() else []:
        d = json.loads(f.read_text())
        out.append({"key": d["key"], "at": d["at"], "n": len(d["decks"]),
                    "label": d["key"].replace("&", " · ").replace("=", ": ") or "Predefinito"})
    return sorted(out, key=lambda x: x["at"], reverse=True)


def build_data(src: str = "hs", ds: str | None = None) -> dict:
    coll, coll_f = None, Path("data/collection.json")
    if coll_f.exists():
        accs = json.loads(coll_f.read_text())
        acc = max(accs.values(), key=lambda a: len(a.get("collection", {})), default=None)
        if acc:
            coll = {"cards": {k: sum(v) for k, v in acc["collection"].items()}, "dust": acc.get("dust", 0)}
    schema = json.loads(SCHEMA_F.read_text()) if SCHEMA_F.exists() else None
    datasets = {"hs": list_hs(), "guru": list_guru()}
    lst = datasets[src]
    sel = next((x for x in lst if x["key"] == ds), None) or (lst[0] if lst else None)
    decks, used, extra = [], {}, {}
    if sel and src == "hs":
        d = json.loads((HS_DIR / f"{sel['key']}.json").read_text())
        decks, used = parse_hs(d["meta"], d["params"]["GameType"] == "RANKED_WILD")
        win = store.windows(sel["key"], decks)
        for x in decks:
            x["w"] = win.get(x["id"], {})
        extra = {"as_of": d["meta"].get("as_of")}
    elif sel and src == "guru":
        allcards = cardmod.load_cards()
        d = json.loads(_file_guru(sel["key"]).read_text())
        decks = d["decks"]
        for x in decks:
            for i, _ in x["cards"]:
                used[i] = cardmod.card_info(allcards[i])
        extra = {"url": d.get("url"), "query": d["key"]}
    return {"src": src, "sel": sel and sel["key"], "selInfo": sel, "datasets": datasets, "schema": schema,
            "hsOptions": {k: [{"value": v, "label": l, "locked": p} for v, l, p in o] for k, o in HS_OPTIONS.items()},
            "decks": decks, "cards": used, "collection": coll, **extra}


SNIPPET = r"""(async()=>{const g=async u=>{const r=await fetch(u,{credentials:'include'});if(!r.ok)throw new Error(r.status===403?'Questo filtro richiede HSReplay Premium':u.split('?')[0]+' '+r.status);return r.json()};
try{const meta=await g('/analytics/query/list_decks_by_win_rate_v2/?GameType=__GT__&LeagueRankRange=__RR__&Region=ALL&TimeRange=__TR__');
let arch=[];try{arch=await g('/api/v1/archetypes/')}catch(e){}
const col={};try{const acc=await g('/api/v1/account/');for(const b of acc.blizzard_accounts||[]){for(const base of ['/api/v1/collection/','https://api.hsreplay.net/v1/collection/']){try{col[b.account_hi+'_'+b.account_lo]=await g(base+'?account_hi='+b.account_hi+'&account_lo='+b.account_lo+'&format=json');break}catch(e){}}}}catch(e){console.warn('collezione:',e.message)}
const r=await fetch('http://127.0.0.1:__PORT__/api/ingest',{method:'POST',body:JSON.stringify({params:{GameType:'__GT__',LeagueRankRange:'__RR__',TimeRange:'__TR__'},meta,arch,col})});
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
const fields=[],names=new Set();
document.querySelectorAll('select[name],form input[name]').forEach(el=>{
 const n=el.name;if(!n||n.startsWith('_')||names.has(n)||el.type==='hidden'||el.type==='submit')return;names.add(n);
 const lab=(el.id&&document.querySelector('label[for="'+el.id+'"]'))||el.closest('label')||(el.parentElement&&el.parentElement.querySelector('label'));
 const label=((lab&&lab.innerText)||'').trim()||n;
 if(el.tagName==='SELECT')fields.push({name:n,label,type:'select',value:el.value,options:[...el.options].map(o=>({value:o.value,label:o.text.trim()}))});
 else fields.push({name:n,label,type:el.type==='checkbox'?'checkbox':'text',value:el.type==='checkbox'?(el.checked?el.value:''):el.value})});
const r=await fetch('http://127.0.0.1:__PORT__/api/ingest_guru',{method:'POST',body:JSON.stringify({url:location.href,rows,schema:fields})});
console.log(r.ok?'HS Deck Matcher: '+rows.length+' deck inviati da HSGuru. Torna alla scheda dell\'app.':'Errore app '+r.status)}catch(e){console.error('HS Deck Matcher:',e.message)}})();"""

_NUM = re.compile(r"\d[\d.,]*")


def _name(text: str) -> str:
    words = []
    for w in text.replace("#", " ").split():
        if re.search(r"\d|%", w) or len(words) >= 4:
            break
        words.append(w)
    return " ".join(words)


def parse_guru(body: dict) -> dict:
    """Decodifica i deck code trovati nella pagina HSGuru."""
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
        text = re.sub(r"\s+", " ", (r.get("text") or "").replace(r["code"], " ")).strip()
        pct = [float(x) for x in re.findall(r"(\d{1,3}(?:[.,]\d+)?)\s*%", text.replace(",", "."))]
        wr = r.get("wr") if r.get("wr") is not None else next((x for x in pct if 20 <= x <= 90), None)
        nums = [int(n.replace(",", "").replace(".", "")) for n in _NUM.findall(re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", text)) if n.strip(",.")]
        games = r.get("games") if r.get("games") is not None else max([n for n in nums if n >= 30] or [0])
        decks.append({"id": r["code"], "cls": cls, "name": (r.get("name") or "").lstrip("# ").strip() or _name(text) or cls.title(),
                      "games": games, "wr": wr if wr is not None else 0, "cards": cl, "code": r["code"], "w": {}, "raw": text})
    return {"decks": decks, "url": body.get("url"), "bad": bad, "n": len(body.get("rows", []))}


def ingest_guru(body: dict):
    out = parse_guru(body)
    out.update(key=guru_key(body.get("url", "")), at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    GURU_DIR.mkdir(parents=True, exist_ok=True)
    _file_guru(out["key"]).write_text(json.dumps(out))
    if body.get("schema"):
        SCHEMA_F.write_text(json.dumps(body["schema"]))
    STATE.update(msg="Dati ricevuti", error=None, last={"src": "guru", "key": out["key"]})


def ingest(body: dict):
    p = hs_params(body["params"])
    key = hs_key(p)
    HS_DIR.mkdir(parents=True, exist_ok=True)
    (HS_DIR / f"{key}.json").write_text(json.dumps({"params": p, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": body["meta"]}))
    Path("data/archetypes.json").write_text(json.dumps(body.get("arch") or []))
    if body.get("col"):
        Path("data/collection.json").write_text(json.dumps(body["col"]))
    decks, _ = parse_hs(body["meta"], p["GameType"] == "RANKED_WILD")
    store.save(key, body["meta"]["as_of"], decks)
    STATE.update(msg="Dati ricevuti", error=None, last={"src": "hs", "key": key})


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body: bytes, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                self._send(TEMPLATE.read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/api/data":
                self._send(json.dumps(build_data(q.get("src", "hs"), q.get("ds"))).encode())
            elif u.path == "/api/snippet":
                STATE["msg"] = ""
                p = hs_params({"GameType": q.get("gt", "RANKED_STANDARD"), "LeagueRankRange": q.get("rr", "BRONZE_THROUGH_GOLD"),
                               "TimeRange": q.get("tr", "CURRENT_PATCH")})
                js = SNIPPET.replace("__GT__", p["GameType"]).replace("__RR__", p["LeagueRankRange"]) \
                    .replace("__TR__", p["TimeRange"]).replace("__PORT__", str(PORT))
                self._send(js.encode(), "text/plain; charset=utf-8")
            elif u.path == "/api/snippet_guru":
                STATE["msg"] = ""
                self._send(GURU_SNIPPET.replace("__PORT__", str(PORT)).encode(), "text/plain; charset=utf-8")
            elif u.path == "/api/status":
                self._send(json.dumps(STATE).encode())
            else:
                self._send(b"{}", code=404)
        except ValueError as e:
            self._send(json.dumps({"error": str(e)}).encode(), code=400)

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
    migrate()
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{port}/"
    print("HS Deck Matcher su", url, "(Ctrl+C per uscire)")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
