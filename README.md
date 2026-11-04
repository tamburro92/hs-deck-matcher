# HS Deck Matcher

App **locale** per Hearthstone: prende le liste meta da HSReplay e HSGuru, le confronta con la tua collezione e le classifica per winrate e **polvere mancante**. Risponde a "quali deck forti posso costruire adesso, e quali mi mancano per pochissimo?".

> Progetto non ufficiale, non affiliato a Blizzard, HSReplay o HSGuru. Tutti i dati restano sul tuo computer.

## Cosa fa

- Classifica i deck per winrate (anche "affidabile", limite inferiore di Wilson), partite, polvere mancante e rapporto qualità/prezzo.
- Calcola le carte mancanti dalla tua collezione (normali + dorate) e il costo in polvere (40 / 100 / 400 / 1600 per comune, rara, epica, leggendaria). Le carte gratuite (Core e simili) non contano.
- Fasce di polvere (0, ≤400, ≤800, ≤1600, ≤3200, ≤6400, tutti) con allargamento automatico se non trova deck, e "solo ciò che posso permettermi".
- Filtri per formato, rank e periodo come sui siti: ogni combinazione è un dataset importato a parte. In più classi, ricerca per nome o carta, "contiene" / "senza" una carta, partite e winrate minimi.
- Finestre "ultimo giorno / ultimi 7 giorni" ricavate dalle differenze tra importazioni successive (HSReplay le offre solo con Premium).
- Un clic su un deck mostra la lista carte (✓ che hai, ✗ da craftare) e copia il deck code per importarlo in gioco.
- Due tab, **HSReplay** e **HSGuru**, con filtri indipendenti.

## Requisiti

- macOS, Linux o Windows con [uv](https://docs.astral.sh/uv/) (Python 3.12+).
- Chrome (o un altro browser) dove sei già loggato su hsreplay.net con la collezione sincronizzata (ad esempio da HSTracker / Hearthstone Deck Tracker).

## Avvio

```bash
uv sync
uv run python -m hsmatcher
```

Si apre `http://127.0.0.1:8765/`. Per non aprire il browser: `--no-open`. Test: `uv run pytest -q`.

## Come si importano i dati

Hsreplay.net e hsguru.com sono protetti da Cloudflare e non si possono interrogare da uno script. L'app non aggira le verifiche: i dati li legge **il tuo browser**, già autenticato, e li passa all'app locale.

1. Nella pagina scegli i filtri e premi il pulsante di importazione. L'app apre il sito e copia negli appunti un piccolo snippet.
2. Nella scheda del sito apri la console (Cmd+Opt+J su Mac, Ctrl+Shift+J altrove), incolla e premi Invio. Se Chrome lo chiede, scrivi `allow pasting`.
3. Lo snippet scarica meta e (su HSReplay) collezione e li invia a `127.0.0.1:8765`. La pagina si aggiorna da sola.

Lo snippet non contiene né invia cookie, password o token: legge solo le liste deck e la tua lista carte. Si può leggere da `/api/snippet` prima di incollarlo.

### Limiti senza HSReplay Premium

Il rank Bronzo–Oro con patch o espansione corrente è gratuito. Gli ultimi 7 giorni e i rank Diamante–Leggenda richiedono Premium (nella pagina sono segnati con 🔒). La recenza si approssima con le differenze tra importazioni.

### HSGuru

Non ha un'API: lo snippet legge i deck dalla pagina `hsguru.com/decks` e anche i filtri del suo form, così dalla seconda importazione puoi sceglierli dall'app. I numeri dipendono dai filtri (periodo, rank) usati sul sito, quindi non sono confrontabili con quelli di HSReplay.

## Dove stanno i dati

Tutto in `data/` (escluso da git): dataset importati, collezione, snapshot SQLite per le finestre temporali e cache del database carte ([HearthstoneJSON](https://hearthstonejson.com)). Nessun dato lascia il computer.

## Struttura

```
src/hsmatcher/
  server.py   server locale, dataset, snippet e importazione
  cards.py    database carte, deck code, costi di crafting
  store.py    snapshot SQLite e finestre temporali
templates/index.html   interfaccia (JS vanilla, nessuna dipendenza esterna)
tests/
```

## Idee future

- Tab "Cosa craftare": le carte che sbloccano più deck forti.
- Raggruppamento per archetipo e grafico polvere/winrate.
- Aggiornamento automatico e login OAuth, se HSReplay rilascia le chiavi.

## Licenza

[MIT](LICENSE).

## Note legali

Hearthstone è un marchio di Blizzard Entertainment. I dati delle carte vengono da HearthstoneJSON; le statistiche dei deck sono dei rispettivi siti e qui vengono solo mostrate in locale per uso personale. Rispetta i termini d'uso di HSReplay e HSGuru.
