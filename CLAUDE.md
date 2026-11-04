# HS Deck Matcher

App locale (Python + pagina HTML) che classifica i deck meta di Hearthstone in base alla collezione dell'utente: winrate, polvere mancante, costruibilità. Lingua del progetto: italiano.

## Comandi

```bash
uv sync                          # installa le dipendenze
uv run python -m hsmatcher       # avvia il server su http://127.0.0.1:8765/ (--no-open per non aprire il browser)
uv run pytest -q                 # test
```

## Architettura

- `src/hsmatcher/server.py`: server `http.server` (nessun framework), `build_data()` che unisce meta, collezione e snapshot, snippet JS serviti da `/api/snippet` e `/api/snippet_guru`, endpoint `/api/ingest` e `/api/ingest_guru`.
- `src/hsmatcher/cards.py`: database carte HearthstoneJSON (`cards.json` completo, cache 7 giorni), deck code con la libreria `hearthstone`, costi di crafting (40/100/400/1600).
- `src/hsmatcher/store.py`: snapshot SQLite del meta e finestre "ultimo giorno / 7 giorni" ricavate dalle differenze tra snapshot.
- `templates/index.html`: pagina unica (JS vanilla); i calcoli di polvere, fasce e filtri sono lato browser. Due tab (HSReplay, HSGuru) con filtri separati.
- `data/` (gitignored): `meta.json`, `collection.json`, `guru.json`, `snapshots.sqlite`, cache carte.

## Come arrivano i dati (importante)

Cloudflare blocca curl, httpx e Playwright su hsreplay.net e hsguru.com. **Non aggirare le verifiche anti-bot.** Il flusso scelto: il pulsante nella pagina apre il sito nel Chrome dell'utente (già loggato), copia negli appunti uno snippet che l'utente incolla nella console; lo snippet fa le fetch dal browser e fa POST a `127.0.0.1:8765/api/ingest*` (CORS ristretto a hsreplay.net / hsguru.com).

- HSReplay: endpoint interno `/analytics/query/list_decks_by_win_rate_v2/` (Standard, `BRONZE_THROUGH_GOLD`, `CURRENT_PATCH`). Senza Premium non esistono `LAST_1_DAY`, `LAST_7_DAYS` né i rank Diamond/Legend (403/400). La collezione viene da `/api/v1/collection/?account_hi&account_lo` con la sessione del browser; la lista account da `/api/v1/account/`.
- HSGuru: nessuna API; lo snippet legge il DOM (`.card` → `.deck-title a`, `[data-clipboard-text]`, primo `.columns .tag` = winrate, `Games: N`). Se il sito cambia markup, aggiornare `GURU_SNIPPET`.

## Regole

- Nessuna credenziale o token: non leggere, stampare né salvare password, cookie o refresh token. Il `.env` di `~/Desktop/hs` (progetto Gemini) non serve e non va letto.
- Le carte del set `CORE`, `TIME_TRAVEL` e quelle senza rarità sono trattate come gratuite (verificato: i costi pieni coincidono con la polvere mostrata da HSReplay).
- Polvere = somma `max(0, copie_deck − possedute) × costo_rarità`; possedute = normali + dorate.
- Le finestre temporali funzionano solo con snapshot ripetuti; se le partite totali calano è una nuova patch e lo storico si azzera.

## Da fare

- Tab "Cosa craftare" (carte che sbloccano più deck forti), raggruppamento per archetipo, grafico polvere/winrate.
- Aggiornamento automatico (cron) e, se HSReplay rilascia `client_id` OAuth, pulsante "Connetti" senza snippet.
