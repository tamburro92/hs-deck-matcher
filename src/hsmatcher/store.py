import sqlite3, time
from pathlib import Path

DB = Path("data/snapshots.sqlite")
MIN_GAMES = {1: 50, 7: 150}


def _db():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("create table if not exists snap(ts real, as_of text, deck text, games int, wr real)")
    c.execute("create index if not exists ix on snap(deck, ts)")
    return c


def save(as_of: str, decks: list[dict]):
    c = _db()
    last = c.execute("select max(ts) from snap").fetchone()[0]
    if last and c.execute("select as_of from snap where ts=?", (last,)).fetchone()[0] == as_of:
        return  # stessi dati già salvati
    now = time.time()
    # nuova patch: le partite totali calano -> storico non confrontabile
    tot_new = sum(d["games"] for d in decks)
    prev = c.execute("select sum(games) from snap where ts=?", (last,)).fetchone()[0] if last else None
    if prev and tot_new < prev:
        c.execute("delete from snap")
    c.executemany("insert into snap values (?,?,?,?,?)",
                  [(now, as_of, d["id"], d["games"], d["wr"]) for d in decks])
    c.commit()


def windows(decks: list[dict], now: float | None = None) -> dict:
    """{deck_id: {1: [partite, winrate], 7: [...]}} dalle differenze tra snapshot."""
    now = now or time.time()
    c = _db()
    out: dict = {}
    for days, mg in MIN_GAMES.items():
        row = c.execute("select max(ts) from snap where ts <= ?", (now - days * 86400 * 0.8,)).fetchone()[0]
        if not row:
            continue
        base = {d: (g, w) for d, g, w in c.execute("select deck, games, wr from snap where ts=?", (row,))}
        for d in decks:
            b = base.get(d["id"])
            if not b:
                continue
            dg = d["games"] - b[0]
            if dg < mg:
                continue
            wins = d["games"] * d["wr"] / 100 - b[0] * b[1] / 100
            out.setdefault(d["id"], {})[days] = [dg, round(100 * wins / dg, 2)]
    return out
