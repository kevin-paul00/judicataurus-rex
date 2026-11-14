"""Asynchroner Client für die Materialien auf www.parlament.gv.at."""

import re

import httpx
from pydantic import ValidationError

from judicataurus_rex.config import Settings
from judicataurus_rex.parlament.models import (
    DocumentGroup,
    GegenstandPage,
    Materials,
    MaterialsKind,
)
from judicataurus_rex.ris.client import RateLimiter

_LEGISLATIVE_PERIOD = re.compile(r"^[IVXLC]{1,8}$")
_NUMBER = re.compile(r"^\d{1,5}$")
_DOCUMENT_PATH = re.compile(r"^/dokument/[A-Za-z0-9/_.\-]+$")
_EXPLANATIONS = "Erläuterungen"
# Beim Initiativantrag steht die Begründung im Antrag selbst („Initiativantrag (elektr.
# übermittelte Version)“); das gescannte Original hat kein HTML.
_MOTION_TEXT = "Initiativantrag"
_TYPE_SEGMENT: dict[MaterialsKind, str] = {"RV": "I", "IA": "A"}


class ParlamentError(RuntimeError):
    """Fehler beim Abruf von der Website des Parlaments."""


class ParlamentClient:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._base = settings.parlament_base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(
            timeout=settings.timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )
        self._limiter = limiter or RateLimiter(settings.parlament_request_interval_seconds)

    async def aclose(self) -> None:
        await self._http.aclose()

    def gegenstand_url(
        self, legislative_period: str, number: str, kind: MaterialsKind = "RV"
    ) -> str:
        """Öffentliche Seite eines Gegenstands.

        ``RV`` steht für alle Gegenstände mit „d.B.“-Nummer (Regierungsvorlage,
        Ausschussbericht …), ``IA`` für selbständige Anträge („2235/A“).
        """
        if _LEGISLATIVE_PERIOD.fullmatch(legislative_period) is None:
            raise ValueError(f"Ungültige Gesetzgebungsperiode: {legislative_period!r}")
        if _NUMBER.fullmatch(number) is None:
            raise ValueError(f"Ungültige Nummer: {number!r}")
        return f"{self._base}/gegenstand/{legislative_period}/{_TYPE_SEGMENT[kind]}/{number}"

    def document_url(self, path: str) -> str:
        if _DOCUMENT_PATH.fullmatch(path) is None:
            raise ValueError(f"Kein Dokumentpfad des Parlaments: {path!r}")
        return f"{self._base}{path}"

    async def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        async with self._limiter.lock:
            await self._limiter.wait_turn()
            try:
                response = await self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                raise ParlamentError(f"Verbindung zum Parlament fehlgeschlagen: {exc}") from exc
            finally:
                self._limiter.mark()
        if response.status_code != 200:
            raise ParlamentError(f"Parlament antwortete mit HTTP {response.status_code} für {url}.")
        return response

    async def materials(
        self, legislative_period: str, number: str, kind: MaterialsKind = "RV"
    ) -> Materials:
        """Angaben und Dokumentlinks zu einer Regierungsvorlage oder einem Initiativantrag."""
        page_url = self.gegenstand_url(legislative_period, number, kind)
        response = await self._get(page_url, {"json": "true"})
        try:
            page = GegenstandPage.model_validate_json(response.content)
        except ValidationError as exc:
            raise ParlamentError(f"Unerwartetes Antwortformat des Parlaments: {exc}") from exc

        html_url: str | None = None
        pdf_url: str | None = None
        for group in _explanation_groups(page.content.documents, kind):
            for document in group.documents:
                if _DOCUMENT_PATH.fullmatch(document.link) is None:
                    continue
                doc_type = document.type.casefold()
                if doc_type == "html" and html_url is None:
                    html_url = self.document_url(document.link)
                elif doc_type == "pdf" and pdf_url is None:
                    pdf_url = self.document_url(document.link)
            if html_url is not None or pdf_url is not None:
                break

        default_citation = f"{number} d.B." if kind == "RV" else f"{number}/A"
        return Materials(
            kind=kind,
            legislative_period=legislative_period,
            number=number,
            title=page.content.title,
            citation=page.content.zitation or default_citation,
            page_url=page_url,
            explanations_html_url=html_url,
            explanations_pdf_url=pdf_url,
        )

    async def fetch_html(self, url: str) -> str:
        """Lädt ein Dokument (z. B. die Erläuterungen) von www.parlament.gv.at."""
        if not url.startswith(f"{self._base}/dokument/"):
            raise ValueError(f"Keine Dokument-URL des Parlaments: {url!r}")
        response = await self._get(url)
        return response.text


def _explanation_groups(groups: list[DocumentGroup], kind: MaterialsKind) -> list[DocumentGroup]:
    """Die Dokumentgruppen mit den Erläuterungen, die beste zuerst.

    Eigene „Erläuterungen“ gehen vor; beim Initiativantrag ist sonst der Antrag selbst
    (mit der Begründung) die Quelle.
    """
    explanations = [g for g in groups if g.title.strip() == _EXPLANATIONS]
    if kind == "RV":
        return explanations
    motions = [g for g in groups if g.title.strip().startswith(_MOTION_TEXT)]
    return explanations + motions
