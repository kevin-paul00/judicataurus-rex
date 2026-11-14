# Judicataurus Rex

Helper to find Austrian judicature, specialized for myself.

---

## Description

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

## Gesetzestext und Materialien

Unter `/gesetz` (z. B. `/gesetz?norm=UG § 67`) zeigt die App alle Fassungen eines Paragraphen.
Jede Fassung lässt sich anklicken; ohne Auswahl erscheint die heute geltende. In den
Judikatur-Treffern sind die Normen verlinkt und öffnen die Fassung, die am Entscheidungstag galt
(`&stichtag=JJJJ-MM-TT`).

Zur gewählten Fassung zeigt die App die Materialien der Novelle, mit der sie entstanden ist:

1. RIS `Bundesrecht` (`BrKons`): Fassungen und Text des Paragraphen
2. RIS `Bundesrecht` (`BgblAuth`): zum ändernden Bundesgesetzblatt die Gesetzgebungsperiode,
   die Regierungsvorlage bzw. den Initiativantrag, den Ausschussbericht und die Sitzung des
   Nationalrats
3. Parlament (`/gegenstand/<GP>/I/<Nr>?json=true`): die Erläuterungen der Regierungsvorlage.
   Gibt es keine Regierungsvorlage, wird der Initiativantrag geladen
   (`/gegenstand/<GP>/A/<Nr>?json=true`, z. B. 2235/A XXV. GP für BGBl. I Nr. 129/2017);
   dessen „Begründung“ dient als Erläuterungen. Angezeigt werden nur die Abschnitte zum
   gewählten Paragraphen („Zu Z 104 (§ 67 Abs. 2)“), bei Sammelnovellen nur aus dem Artikel des
   richtigen Gesetzes, dazu Links auf die vollständigen Dokumente.

Grenzen: Das authentische Bundesgesetzblatt gibt es im RIS erst ab 2004, ältere Fassungen
haben daher keine Materialien. Die Begründung eines Initiativantrags erläutert den Antrag in
der eingebrachten Fassung. Begründungen für Änderungen im Ausschuss stehen im
Ausschussbericht (nur verlinkt).

### Weiteres Gesetz ergänzen

Ein Eintrag in `KNOWN_LAWS` in `src/judicataurus_rex/ris/laws.py` genügt:

```python
LawAliases(
    canonical="StudFG",
    full_title="Studienförderungsgesetz 1992",   # wie in den Erläuterungen
    gesetzesnummer="10009824",                   # aus der RIS-URL der geltenden Fassung
    names=("StudFG", "Studienförderungsgesetz 1992"),
    fallback=("StudFG",),
),
```

Die Gesetzesnummer steht in der Adresse der geltenden Fassung im RIS
(`…GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=…`).

## Nutzungsbedingungen des RIS

- Lizenz der Daten: CC BY 4.0. Die Quellenangabe steht in der Oberfläche und im ZIP (`QUELLE.txt`).
- Höchstens 0,5 Anfragen pro Sekunde, keine parallelen Verbindungen. Alle Anfragen
  (Suche und PDFs) laufen deshalb über einen gemeinsamen Rate-Limiter mit mindestens 2 s Abstand.
  Ein ZIP mit 50 PDFs dauert also etwa 100 s.
- Massendownloads müssen vorher an `ris.it@bka.gv.at` angekündigt werden.

Die Daten des Parlaments stehen ebenfalls unter CC BY 4.0
(<https://www.parlament.gv.at/recherchieren/open-data/>). Anfragen dorthin laufen über einen
eigenen Rate-Limiter (Standard 1 s Abstand), Fassungen und Materialien werden 24 h gecacht.

## Gestaltung (KP-CD)

Die Oberfläche folgt dem Corporate Design aus `kp-corporate-design`. Farben, Schriften
(IBM Plex), Muster, Favicon und Farbmodus-Umschalter liegen unverändert unter
`src/judicataurus_rex/web/static/kp/`; `static/style.css` verwendet nur die `--kp-…`-Tokens.
Nach einer Änderung am CD dort bauen und hier übernehmen:

```bash
python3 tools/sync_cd.py                      # erwartet ../kp-corporate-design
python3 tools/sync_cd.py --source /pfad/zum/cd
```

Der übernommene Stand steht in `static/kp/CD-VERSION`.

## Konfiguration (Umgebungsvariablen)

| Variable | Default |
|---|---|
| `JR_HOST` / `JR_PORT` | `127.0.0.1` / `8000` |
| `JR_USER_AGENT` | `judicataurus-rex/0.1` |
| `JR_REQUEST_INTERVAL_SECONDS` | `2.0` (Minimum 2.0) |
| `JR_MAX_DOCUMENTS_PER_QUERY` | `1000` |
| `JR_MAX_ZIP_DOCUMENTS` | `100` |
| `JR_CACHE_TTL_SECONDS` | `3600` |
| `JR_PARLAMENT_BASE_URL` | `https://www.parlament.gv.at` |
| `JR_PARLAMENT_REQUEST_INTERVAL_SECONDS` | `1.0` (Minimum 0.5) |
| `JR_LAW_CACHE_TTL_SECONDS` | `86400` |

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
  text.py             fremdes HTML → Textblöcke (ohne Skripte, ohne Screenreader-Dubletten)
  statute.py          Gesetzesansicht: Fassungen, BGBl, Materialien, Cache
  parlament/          Client für parlament.gv.at, Auswahl der passenden Erläuterungen
  web/                FastAPI-Routen, Jinja2-Templates, CSS/JS
tests/                unit/, integration/, fixtures/ (Originalantworten von RIS und Parlament)
```
