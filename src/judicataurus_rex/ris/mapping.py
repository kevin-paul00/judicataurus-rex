"""Umwandlung der RIS-Rohmodelle in Domänenmodelle."""

import re
from datetime import date

from judicataurus_rex.ris.models import (
    DOCUMENT_ID_PATTERN,
    BgblInfo,
    Court,
    Decision,
    DocType,
    LawVersion,
)
from judicataurus_rex.ris.raw_models import DocumentReference


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _doc_type(value: str | None) -> DocType | None:
    match value:
        case "Rechtssatz":
            return DocType.RECHTSSATZ
        case "Text":
            return DocType.TEXT
        case _:
            return None


_MOTION = re.compile(r"^(\d{1,5})\s*/\s*A$")


def _motion_numbers(items: list[str]) -> tuple[str, ...]:
    """Initiativanträge „2235/A“ → ``("2235",)``; andere Formen werden ignoriert."""
    numbers = (m.group(1) for item in items if (m := _MOTION.match(item.strip())))
    return tuple(dict.fromkeys(numbers))


def _case_numbers(items: list[str]) -> tuple[str, ...]:
    # Bei Rechtssätzen steht oft ein einziger String mit ";"-getrennten Zahlen.
    numbers: list[str] = []
    for item in items:
        numbers.extend(part.strip() for part in item.split(";") if part.strip())
    return tuple(dict.fromkeys(numbers))


def _content_url(reference: DocumentReference, data_type: str) -> str | None:
    content = reference.data.dokumentliste.content_reference
    main = [c for c in content if c.content_type == "MainDocument"] or content
    for entry in main:
        for url in entry.urls.content_url:
            if url.data_type.casefold() == data_type:
                return url.url
    return None


def _pdf_url(reference: DocumentReference) -> str | None:
    return _content_url(reference, "pdf")


def _bgbl(organ: str | None, number: str | None) -> str | None:
    if not number:
        return None
    return f"{(organ or 'BGBl. I Nr.').strip()} {number.strip()}"


def to_law_version(reference: DocumentReference) -> LawVersion | None:
    """Rohdokument (BrKons) → :class:`LawVersion`. ``None``, wenn Pflichtangaben fehlen."""
    meta = reference.data.metadaten
    bundesrecht = meta.bundesrecht
    if bundesrecht is None or bundesrecht.br_kons is None:
        return None
    if DOCUMENT_ID_PATTERN.fullmatch(meta.technisch.id) is None:
        return None
    kons = bundesrecht.br_kons
    return LawVersion(
        id=meta.technisch.id,
        title=bundesrecht.kurztitel or kons.abkuerzung or "",
        label=kons.artikel_paragraph_anlage or "",
        valid_from=_parse_date(kons.inkrafttretensdatum),
        valid_to=_parse_date(kons.ausserkrafttretensdatum),
        amending_bgbl=_bgbl(kons.novellen_publikationsorgan, kons.novellen_bgblnummer),
        original_bgbl=_bgbl(kons.stammnorm_publikationsorgan, kons.stammnorm_bgblnummer),
        html_url=_content_url(reference, "html"),
        pdf_url=_pdf_url(reference),
        ris_url=bundesrecht.eli or meta.allgemein.dokument_url,
    )


def to_bgbl_info(reference: DocumentReference) -> BgblInfo | None:
    """Rohdokument (BgblAuth) → :class:`BgblInfo`. ``None``, wenn Pflichtangaben fehlen."""
    meta = reference.data.metadaten
    bundesrecht = meta.bundesrecht
    if bundesrecht is None or bundesrecht.bgbl_auth is None:
        return None
    auth = bundesrecht.bgbl_auth
    if not auth.bgblnummer or DOCUMENT_ID_PATTERN.fullmatch(meta.technisch.id) is None:
        return None
    return BgblInfo(
        id=meta.technisch.id,
        bgbl=auth.bgblnummer,
        title=bundesrecht.kurztitel,
        issue_date=_parse_date(auth.ausgabedatum),
        legislative_period=auth.gesetzgebungsperiode or None,
        rv_numbers=tuple(n.strip() for n in auth.regierungsvorlage.item if n.strip()),
        ab_numbers=tuple(n.strip() for n in auth.ausschussbericht_nationalrat.item if n.strip()),
        ia_numbers=_motion_numbers(auth.initiativantrag.item),
        nr_session=auth.nummer_nationalrat or None,
        nr_session_date=_parse_date(auth.datum_nationalrat),
        ris_url=bundesrecht.eli or meta.allgemein.dokument_url,
    )


def to_decision(reference: DocumentReference, court: Court) -> Decision | None:
    """Rohdokument → :class:`Decision`. ``None``, wenn Pflichtangaben fehlen."""
    meta = reference.data.metadaten
    doc_type = _doc_type(meta.judikatur.dokumenttyp)
    if doc_type is None or DOCUMENT_ID_PATTERN.fullmatch(meta.technisch.id) is None:
        return None
    return Decision(
        id=meta.technisch.id,
        court=court,
        organ=meta.technisch.organ or court.label,
        doc_type=doc_type,
        case_numbers=_case_numbers(meta.judikatur.geschaeftszahl.item),
        decision_date=_parse_date(meta.judikatur.entscheidungsdatum),
        norms=tuple(n.strip() for n in meta.judikatur.normen.item if n.strip()),
        ecli=meta.judikatur.ecli,
        keywords=meta.judikatur.schlagworte,
        ris_url=meta.allgemein.dokument_url,
        pdf_url=_pdf_url(reference),
    )
