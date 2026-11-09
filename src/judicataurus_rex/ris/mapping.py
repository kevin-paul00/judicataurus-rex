"""Umwandlung der RIS-Rohmodelle in Domänenmodelle."""

from datetime import date

from judicataurus_rex.ris.models import DOCUMENT_ID_PATTERN, Court, Decision, DocType
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


def _case_numbers(items: list[str]) -> tuple[str, ...]:
    # Bei Rechtssätzen steht oft ein einziger String mit ";"-getrennten Zahlen.
    numbers: list[str] = []
    for item in items:
        numbers.extend(part.strip() for part in item.split(";") if part.strip())
    return tuple(dict.fromkeys(numbers))


def _pdf_url(reference: DocumentReference) -> str | None:
    content = reference.data.dokumentliste.content_reference
    main = [c for c in content if c.content_type == "MainDocument"] or content
    for entry in main:
        for url in entry.urls.content_url:
            if url.data_type.casefold() == "pdf":
                return url.url
    return None


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
