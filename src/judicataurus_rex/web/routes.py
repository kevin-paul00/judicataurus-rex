"""HTTP-Routen der Weboberfläche."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from judicataurus_rex.config import Settings
from judicataurus_rex.downloads import ATTRIBUTION, build_zip, pdf_filename
from judicataurus_rex.ris import laws
from judicataurus_rex.ris.client import RisError
from judicataurus_rex.ris.models import (
    DEFAULT_COURTS,
    DOCUMENT_ID_PATTERN,
    Court,
    Decision,
    DocType,
    SearchMode,
    SearchRequest,
    SearchResult,
)
from judicataurus_rex.ris.normalize import NormParseError, expand, parse_queries, parse_query
from judicataurus_rex.ris.search import SearchService
from judicataurus_rex.statute import StatuteError, StatuteService, StatuteView

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")

_EXAMPLE_NORMS = "UG § 63\nHSG 2014 § 31"
_EXAMPLE_STATUTE = "UG § 67"


def statute_link(norm: str, as_of: date | None = None) -> str | None:
    """Link zur Gesetzesansicht für einen RIS-Normeintrag wie ``"UG §67 Abs1"``.

    ``None``, wenn das Gesetz (noch) keine Gesetzesansicht hat. Mit ``as_of`` öffnet die
    Ansicht die an diesem Tag geltende Fassung (z. B. am Entscheidungsdatum).
    """
    parsed = expand(norm)
    if not parsed or parsed[0].kind != "§" or parsed[0].number is None:
        return None
    law = laws.lookup(parsed[0].law)
    if law is None or law.gesetzesnummer is None:
        return None
    params = {"norm": f"{law.canonical} § {parsed[0].number}"}
    if as_of is not None:
        params["stichtag"] = as_of.isoformat()
    return "/gesetz?" + urlencode(params)


@dataclass(frozen=True, slots=True)
class Services:
    settings: Settings
    search: SearchService
    statute: StatuteService


@dataclass(frozen=True, slots=True)
class FormState:
    """Formularwerte für das erneute Anzeigen nach einer Suche."""

    norms: str
    courts: frozenset[Court]
    mode: SearchMode
    doc_types: frozenset[DocType]
    date_from: str
    date_to: str


def _parse_courts(values: list[str]) -> tuple[list[Court], list[str]]:
    courts: list[Court] = []
    errors: list[str] = []
    for value in values:
        try:
            court = Court(value)
        except ValueError:
            errors.append(f"Unbekanntes Gericht: {value}")
            continue
        if court not in courts:
            courts.append(court)
    return courts, errors


def _parse_doc_types(values: list[str]) -> list[DocType]:
    return [t for t in DocType if t.value in values]


def _parse_date(value: str, label: str, errors: list[str]) -> date | None:
    if not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        errors.append(f"{label}: ungültiges Datum „{value}“ (Format JJJJ-MM-TT).")
        return None


def _parse_doc_ref(value: str) -> tuple[Court, str]:
    court_raw, _, document_id = value.partition(":")
    try:
        court = Court(court_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unbekanntes Gericht: {court_raw}") from exc
    if DOCUMENT_ID_PATTERN.fullmatch(document_id) is None:
        raise HTTPException(status_code=400, detail=f"Ungültige Dokumentnummer: {document_id}")
    return court, document_id


def build_router(services: Services) -> APIRouter:
    router = APIRouter()
    settings = services.settings

    @router.get("/", response_class=HTMLResponse)
    async def index(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        norms: Annotated[str | None, Query()] = None,
        court: Annotated[list[str] | None, Query()] = None,
        mode: Annotated[str, Query()] = "or",
        doc_type: Annotated[list[str] | None, Query()] = None,
        date_from: Annotated[str, Query()] = "",
        date_to: Annotated[str, Query()] = "",
    ) -> HTMLResponse:
        searched = norms is not None
        errors: list[str] = []
        courts, court_errors = _parse_courts(court or [])
        errors.extend(court_errors)
        doc_types = _parse_doc_types(doc_type or [])
        search_mode: SearchMode = "and" if mode == "and" else "or"

        state = FormState(
            norms=norms if norms is not None else _EXAMPLE_NORMS,
            courts=frozenset(courts if searched else DEFAULT_COURTS),
            mode=search_mode,
            doc_types=frozenset(doc_types if searched else DocType),
            date_from=date_from,
            date_to=date_to,
        )

        result: SearchResult | None = None
        if searched:
            queries, norm_errors = parse_queries(norms or "")
            errors.extend(norm_errors)
            parsed_from = _parse_date(date_from, "Datum von", errors)
            parsed_to = _parse_date(date_to, "Datum bis", errors)
            if not queries and not norm_errors:
                errors.append("Bitte mindestens eine Norm eingeben.")
            if not courts:
                errors.append("Bitte mindestens ein Gericht auswählen.")
            if not doc_types:
                errors.append("Bitte mindestens einen Dokumenttyp auswählen.")
            if not errors:
                search_request = SearchRequest(
                    norms=tuple(queries),
                    courts=tuple(courts),
                    mode=search_mode,
                    doc_types=tuple(doc_types),
                    date_from=parsed_from,
                    date_to=parsed_to,
                )
                try:
                    result = await services.search.search(search_request)
                except RisError as exc:
                    errors.append(str(exc))

        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "state": state,
                "all_courts": list(Court),
                "all_doc_types": list(DocType),
                "result": result,
                "errors": errors,
                "searched": searched,
                "active": "judikatur",
                "statute_link": statute_link,
                "attribution": ATTRIBUTION,
                "max_zip": settings.max_zip_documents,
                "interval": settings.request_interval_seconds,
            },
        )

    @router.get("/gesetz", response_class=HTMLResponse)
    async def statute(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        norm: Annotated[str | None, Query()] = None,
        fassung: Annotated[str | None, Query()] = None,
        stichtag: Annotated[str, Query()] = "",
    ) -> HTMLResponse:
        errors: list[str] = []
        view: StatuteView | None = None
        if norm is not None:
            as_of = _parse_date(stichtag, "Stichtag", errors)
            version_id = fassung if fassung and DOCUMENT_ID_PATTERN.fullmatch(fassung) else None
            if fassung and version_id is None:
                errors.append(f"Ungültige Fassung: {fassung}")
            try:
                query = parse_query(norm)
            except NormParseError as exc:
                errors.append(str(exc))
            else:
                if not errors:
                    try:
                        view = await services.statute.view(query, version_id, as_of)
                    except StatuteError as exc:
                        errors.append(str(exc))

        norm_text = (
            f"{view.law.canonical} § {view.paragraph}"
            if view is not None
            else (norm if norm is not None else _EXAMPLE_STATUTE)
        )
        return TEMPLATES.TemplateResponse(
            request,
            "gesetz.html",
            {
                "norm_text": norm_text,
                "active": "gesetz",
                "view": view,
                "errors": errors,
                "today": date.today(),
                "available": [lw.canonical for lw in laws.KNOWN_LAWS if lw.gesetzesnummer],
                "attribution": ATTRIBUTION,
                "interval": settings.request_interval_seconds,
            },
        )

    @router.get("/pdf/{court}/{document_id}")
    async def pdf(court: str, document_id: str) -> Response:  # pyright: ignore[reportUnusedFunction]
        parsed_court, parsed_id = _parse_doc_ref(f"{court}:{document_id}")
        try:
            content = await services.search.client.fetch_pdf(parsed_court, parsed_id)
        except RisError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        decision: Decision | None = services.search.known_decision(parsed_id)
        filename = pdf_filename(parsed_court, parsed_id, decision)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/zip")
    async def zip_download(  # pyright: ignore[reportUnusedFunction]
        doc: Annotated[list[str], Form()],
    ) -> Response:
        refs = list(dict.fromkeys(doc))
        if len(refs) > settings.max_zip_documents:
            raise HTTPException(
                status_code=400,
                detail=f"Höchstens {settings.max_zip_documents} Dokumente pro ZIP "
                f"(ausgewählt: {len(refs)}).",
            )
        items: list[tuple[Court, str, Decision | None]] = []
        for ref in refs:
            court, document_id = _parse_doc_ref(ref)
            items.append((court, document_id, services.search.known_decision(document_id)))

        result = await build_zip(services.search.client, items)
        if result.added == 0:
            raise HTTPException(
                status_code=502,
                detail="Kein PDF konnte geladen werden: " + "; ".join(result.errors),
            )
        stamp = date.today().isoformat()
        return Response(
            content=result.content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="judikatur_{stamp}.zip"',
                "X-Documents-Added": str(result.added),
                "X-Documents-Failed": str(len(result.errors)),
            },
        )

    return router
