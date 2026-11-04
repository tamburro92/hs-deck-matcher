import functools, json, time
from pathlib import Path
import httpx
from hearthstone.deckstrings import Deck
from hearthstone.enums import FormatType

DATA = Path("data")
URL = "https://api.hearthstonejson.com/v1/latest/enUS/cards.json"
HEROES = {"DEATHKNIGHT": 78065, "DEMONHUNTER": 56550, "DRUID": 274, "HUNTER": 31, "MAGE": 637,
          "PALADIN": 671, "PRIEST": 813, "ROGUE": 930, "SHAMAN": 1066, "WARLOCK": 893, "WARRIOR": 7}
CRAFT = {"COMMON": 40, "RARE": 100, "EPIC": 400, "LEGENDARY": 1600}


@functools.cache
def load_cards() -> dict[int, dict]:
    f = DATA / "cards.json"
    if not f.exists() or time.time() - f.stat().st_mtime > 7 * 86400:
        DATA.mkdir(exist_ok=True)
        r = httpx.get(URL, follow_redirects=True, timeout=60)
        r.raise_for_status()
        f.write_bytes(r.content)
    return {c["dbfId"]: c for c in json.loads(f.read_bytes())}


def deckstring(cls: str, cards: list[list[int]], fmt=FormatType.FT_STANDARD) -> str:
    d = Deck()
    d.heroes = [HEROES[cls]]
    d.format = fmt
    d.cards = [(int(i), int(n)) for i, n in cards]
    return d.as_deckstring


def card_info(c: dict) -> list:
    """[nome, costo craft, gratis, mana]: Core/Basic sono gratis per tutti."""
    free = c.get("set") == "CORE" or c.get("rarity") in (None, "FREE")
    return [c["name"], CRAFT.get(c.get("rarity"), 0), free, c.get("cost", 0)]
