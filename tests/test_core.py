import time
from hearthstone.deckstrings import Deck
from hsmatcher import cards, store


def test_deckstring_roundtrip():
    code = cards.deckstring("MAGE", [[1004, 2], [1005, 1]])
    d = Deck.from_deckstring(code)
    assert d.heroes == [637] and sorted(d.cards) == [(1004, 2), (1005, 1)]


def test_window_from_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "s.sqlite")
    c = store._db()
    now = time.time()
    c.execute("insert into snap values (?,?,?,?,?)", (now - 2 * 86400, "a", "x", 1000, 50.0))
    c.commit()
    out = store.windows([{"id": "x", "games": 1400, "wr": 55.0}], now)
    assert out["x"][1] == [400, 67.5]
