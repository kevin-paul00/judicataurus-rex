"""Asynchroner Client für die RIS-OGD-Schnittstelle.

Nutzungsbedingungen (https://data.bka.gv.at/ris/api/v2.6/): höchstens 0,5 Anfragen
pro Sekunde und keine parallelen Verbindungen. Deshalb laufen **alle** Anfragen,
Suche wie PDF-Download, über einen gemeinsamen :class:`RateLimiter`.
"""

import asyncio
import re
import time
from collections.abc import Callable
from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from judicataurus_rex.config import Settings
from judicataurus_rex.ris.mapping import to_bgbl_info, to_decision, to_law_version
from judicataurus_rex.ris.models import DOCUMENT_ID_PATTERN, BgblInfo, Court, Decision, LawVersion
from judicataurus_rex.ris.raw_models import DocumentReference, Envelope

PAGE_SIZE = 100
_PAGE_SIZE_PARAM = "OneHundred"
_PAGE_OUT_OF_RANGE = "Seitennummer ist höher"
_DOCUMENT_HOST = "https://ogd.ris.bka.gv.at/"
_GESETZESNUMMER = re.compile(r"^\d{8}$")
_BGBL = re.compile(r"BGBl\.\s*(?P<part>I{1,3})\s*Nr\.\s*(?P<number>\d+)/(?P<year>\d{4})")


class RisError(RuntimeError):
    """Fehler der RIS-Schnittstelle oder der Verbindung dorthin."""


class RateLimiter:
    """Serialisiert Anfragen und hält einen Mindestabstand zwischen ihnen ein."""

    def __init__(
        self, interval_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._interval = interval_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._last: float | None = None

    @property
    def interval_seconds(self) -> float:
        return self._interval

    @property
    def lock(self) -> asyncio.Lock:
        """Während eine Anfrage läuft, wird dieser Lock gehalten (keine Parallelität)."""
        return self._lock

    async def wait_turn(self) -> None:
        """Muss mit gehaltenem :attr:`lock` aufgerufen werden."""
        if self._last is not None:
            delay = self._interval - (self._clock() - self._last)
            if delay > 0:
                await asyncio.sleep(delay)

    def mark(self) -> None:
        self._last = self._clock()


class Page(BaseModel):
    """Eine Ergebnisseite der Judikatursuche."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    total: int
    page_number: int
    decisions: tuple[Decision, ...]
    skipped: int = 0


class RisClient:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(
            timeout=settings.timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )
        self._limiter = limiter or RateLimiter(settings.request_interval_seconds)
        self._request_count = 0

    @property
    def request_count(self) -> int:
        """Anzahl der bisher gesendeten HTTP-Anfragen (für Statistik/Anzeige)."""
        return self._request_count

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        async with self._limiter.lock:
            await self._limiter.wait_turn()
            try:
                response = await self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                raise RisError(f"Verbindung zum RIS fehlgeschlagen: {exc}") from exc
            finally:
                self._limiter.mark()
                self._request_count += 1
        if response.status_code != 200:
            raise RisError(f"RIS antwortete mit HTTP {response.status_code} für {url}.")
        return response

    async def search_page(
        self,
        court: Court,
        norm: str,
        page_number: int = 1,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Page:
        """Eine Seite (bis zu 100 Dokumente) für einen ``Norm``-Suchbegriff."""
        params: dict[str, str] = {
            "Applikation": court.value,
            "Norm": norm,
            # Ohne diese Flags liefert z. B. die Justiz nur Rechtssätze.
            "Dokumenttyp.SucheInRechtssaetzen": "true",
            "Dokumenttyp.SucheInEntscheidungstexten": "true",
            "DokumenteProSeite": _PAGE_SIZE_PARAM,
            "Seitennummer": str(page_number),
            "Sortierung.SortedByColumn": "Datum",
            "Sortierung.SortDirection": "Descending",
        }
        if date_from is not None:
            params["EntscheidungsdatumVon"] = date_from.isoformat()
        if date_to is not None:
            params["EntscheidungsdatumBis"] = date_to.isoformat()

        total, references = await self._query("Judikatur", params)
        decisions: list[Decision] = []
        skipped = 0
        for reference in references:
            decision = to_decision(reference, court)
            if decision is None:
                skipped += 1
            else:
                decisions.append(decision)
        return Page(
            total=total,
            page_number=page_number,
            decisions=tuple(decisions),
            skipped=skipped,
        )

    async def _query(
        self, endpoint: str, params: dict[str, str]
    ) -> tuple[int, list[DocumentReference]]:
        """Eine Suchanfrage; gibt (Gesamttreffer, Dokumente dieser Seite) zurück."""
        response = await self._get(f"{self._settings.api_base_url}/{endpoint}", params)
        try:
            envelope = Envelope.model_validate_json(response.content)
        except ValidationError as exc:
            raise RisError(f"Unerwartetes Antwortformat des RIS: {exc}") from exc

        body = envelope.body
        if body.error is not None:
            if _PAGE_OUT_OF_RANGE in body.error.message:
                return 0, []
            raise RisError(f"RIS-Fehler: {body.error.message}")
        if body.results is None:
            raise RisError("RIS-Antwort enthält weder Ergebnisse noch Fehlermeldung.")
        return _to_int(body.results.hits.total), body.results.references

    async def law_versions(self, gesetzesnummer: str, paragraph: str) -> list[LawVersion]:
        """Alle Fassungen eines Paragraphen (ältste zuerst)."""
        if _GESETZESNUMMER.fullmatch(gesetzesnummer) is None:
            raise ValueError(f"Ungültige Gesetzesnummer: {gesetzesnummer!r}")
        versions: dict[str, LawVersion] = {}
        page_number = 1
        while True:
            params = {
                "Applikation": "BrKons",
                "Gesetzesnummer": gesetzesnummer,
                "Abschnitt.Typ": "Paragraph",
                "Abschnitt.Von": paragraph,
                "Abschnitt.Bis": paragraph,
                "DokumenteProSeite": _PAGE_SIZE_PARAM,
                "Seitennummer": str(page_number),
            }
            total, references = await self._query("Bundesrecht", params)
            for reference in references:
                version = to_law_version(reference)
                # Abschnitt.Von/Bis liefert auch "§ 67a"; nur exakte Treffer behalten.
                if version is not None and _same_paragraph(version.label, paragraph):
                    versions[version.id] = version
            if not references or page_number * PAGE_SIZE >= total:
                break
            page_number += 1
        return sorted(versions.values(), key=lambda v: (v.valid_from or date.min, v.id))

    async def bgbl_info(self, bgbl: str) -> BgblInfo | None:
        """Metadaten eines Bundesgesetzblatts, z. B. ``"BGBl. I Nr. 93/2021"``.

        ``None``, wenn das Blatt nicht im authentischen BGBl (ab 2004) steht.
        """
        match = _BGBL.search(bgbl)
        if match is None:
            return None
        part, number, year = match.group("part"), match.group("number"), match.group("year")
        params = {
            "Applikation": "BgblAuth",
            "Bgblnummer": f"{number}/{year}",
            "Teil": str(len(part)),
        }
        _, references = await self._query("Bundesrecht", params)
        wanted_id = f"BGBLA_{year}_{part}_{number}"
        for reference in references:
            if reference.data.metadaten.technisch.id == wanted_id:
                return to_bgbl_info(reference)
        return None

    async def fetch_html(self, url: str) -> str:
        """Lädt ein HTML-Dokument (z. B. den Text einer Fassung) aus dem RIS."""
        if not url.startswith(_DOCUMENT_HOST):
            raise ValueError(f"Keine RIS-Dokument-URL: {url!r}")
        response = await self._get(url)
        return response.text

    def pdf_url(self, court: Court, document_id: str) -> str:
        if DOCUMENT_ID_PATTERN.fullmatch(document_id) is None:
            raise ValueError(f"Ungültige Dokumentnummer: {document_id!r}")
        base = self._settings.document_base_url
        return f"{base}/{court.value}/{document_id}/{document_id}.pdf"

    async def fetch_pdf(self, court: Court, document_id: str) -> bytes:
        response = await self._get(self.pdf_url(court, document_id))
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.casefold():
            raise RisError(f"Kein PDF für {document_id} verfügbar (Content-Type: {content_type}).")
        return response.content


def _same_paragraph(label: str, paragraph: str) -> bool:
    """``"§ 67"`` passt zu ``"67"``, ``"§ 67a"`` nicht."""
    return label.replace("§", "").strip().casefold() == paragraph.strip().casefold()


def _to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise RisError(f"Ungültige Trefferanzahl im RIS: {value!r}") from exc
