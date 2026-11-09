# Judicataurus Rex

Sucht zu einer oder mehreren Rechtsnormen die passende Judikatur im
[RIS](https://www.ris.bka.gv.at), listet die Treffer auf und bietet die PDFs einzeln
oder gesammelt als ZIP an. Der Fokus liegt auf dem Hochschulrecht (UG, HSG 2014) beim
BVwG, VwGH und VfGH. Die Justiz (OGH), die LVwG und die DSB können ebenfalls ausgewählt werden.

Datenquelle ist die offizielle **RIS-OGD-Schnittstelle v2.6**
(`https://data.bka.gv.at/ris/api/v2.6/Judikatur`).

## Start

```bash
uv sync
uv run judicataurus-rex          # http://127.0.0.1:8000
```

## Normen eingeben

Eine Norm pro Zeile, z. B. `UG § 63`, `§ 63 Abs 1 Z 3 UG`, `HSG 2014` (ganzes Gesetz)
oder `B-VG Art 133`. Mehrere Normen lassen sich mit **ODER** (mindestens eine) oder
**UND** (alle) verknüpfen.

Die Gerichte zitieren Gesetze unterschiedlich: Das BVwG schreibt `UG §63`, VwGH und
VfGH schreiben `UniversitätsG 2002 §63`. Für UG und HSG 2014 übersetzt
`src/judicataurus_rex/ris/laws.py` das automatisch, weitere Gesetze lassen sich dort
ergänzen. Absatz und Ziffer werden lokal gegen das Feld `Normen` der Dokumente
geprüft, auch bei Sammelangaben wie `UniversitätsG 2002 §51 Abs2, §63 Abs1`.

## Nutzungsbedingungen des RIS

- Lizenz der Daten: CC BY 4.0. Die Quellenangabe steht in der Oberfläche und im ZIP (`QUELLE.txt`).
- Höchstens 0,5 Anfragen pro Sekunde, keine parallelen Verbindungen. Alle Anfragen
  (Suche und PDFs) laufen deshalb über einen gemeinsamen Rate-Limiter mit mindestens 2 s Abstand.
  Ein ZIP mit 50 PDFs dauert also etwa 100 s.
- Massendownloads müssen vorher an `ris.it@bka.gv.at` angekündigt werden.

## Konfiguration (Umgebungsvariablen)

| Variable | Default |
|---|---|
| `JR_HOST` / `JR_PORT` | `127.0.0.1` / `8000` |
| `JR_USER_AGENT` | `judicataurus-rex/0.1` |
| `JR_REQUEST_INTERVAL_SECONDS` | `2.0` (Minimum 2.0) |
| `JR_MAX_DOCUMENTS_PER_QUERY` | `1000` |
| `JR_MAX_ZIP_DOCUMENTS` | `100` |
| `JR_CACHE_TTL_SECONDS` | `3600` |

## Entwicklung

```bash
uv run basedpyright      # strict (entspricht Pylance "strict")
uv run ruff check && uv run ruff format --check
uv run pytest            # Tests unter tests/unit und tests/integration
```

Für Tests lassen sich `RisClient` (mit eigenem `httpx.AsyncClient`/`RateLimiter`) und
`create_app(settings, client)` injizieren. `respx` ist als Dev-Abhängigkeit installiert.

## Aufbau

```
src/judicataurus_rex/
  config.py           Einstellungen (strict, aus JR_*-Variablen)
  downloads.py        PDF-Dateinamen, ZIP mit uebersicht.csv
  ris/raw_models.py   Pydantic-Modelle der RIS-JSON (XML→JSON-Eigenheiten)
  ris/models.py       Domänenmodelle (Court, Decision, SearchRequest …)
  ris/mapping.py      Rohmodell → Decision
  ris/laws.py         Zitierweisen je Gericht
  ris/normalize.py    Normen parsen, API-Begriffe, lokaler Abgleich
  ris/client.py       httpx-Client mit Rate-Limiter
  ris/search.py       UND/ODER-Suche, Paging, Cache
  web/                FastAPI-Routen, Jinja2-Templates, CSS/JS
tests/                unit/, integration/ (noch keine Tests)
```
