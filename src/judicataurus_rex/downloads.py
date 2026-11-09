"""PDF-Downloads: Dateinamen und ZIP-Archive."""

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime

from judicataurus_rex.ris.client import RisClient, RisError
from judicataurus_rex.ris.models import Court, Decision

_UNSAFE = re.compile(r"[^\w.-]+", re.UNICODE)

ATTRIBUTION = (
    "Quelle: Rechtsinformationssystem des Bundes (RIS), https://www.ris.bka.gv.at, "
    "abgerufen über die OGD-Schnittstelle; Lizenz: CC BY 4.0."
)


def _safe(text: str, limit: int = 60) -> str:
    return _UNSAFE.sub("_", text).strip("_")[:limit]


def pdf_filename(court: Court, document_id: str, decision: Decision | None) -> str:
    """Sprechender Dateiname, z. B. ``2026-08-31_Bvwg_W129_2323711-1_BVWGT_….pdf``."""
    if decision is None:
        return f"{court.value}_{document_id}.pdf"
    parts: list[str] = []
    if decision.decision_date is not None:
        parts.append(decision.decision_date.isoformat())
    parts.append(court.value)
    if decision.case_numbers:
        parts.append(_safe(decision.case_numbers[0]))
    parts.append(document_id)
    return "_".join(p for p in parts if p) + ".pdf"


@dataclass(slots=True)
class ZipResult:
    content: bytes
    added: int
    errors: list[str] = field(default_factory=list[str])


async def build_zip(
    client: RisClient,
    items: list[tuple[Court, str, Decision | None]],
) -> ZipResult:
    """Lädt die PDFs nacheinander (rate-limitiert) und packt sie in ein ZIP.

    Das ZIP enthält zusätzlich ``uebersicht.csv`` mit den Metadaten und, falls
    Downloads fehlschlagen, ``fehler.txt``.
    """
    buffer = io.BytesIO()
    errors: list[str] = []
    added = 0
    index_rows: list[list[str]] = []

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        used_names: set[str] = set()
        for court, document_id, decision in items:
            try:
                pdf = await client.fetch_pdf(court, document_id)
            except (RisError, ValueError) as exc:
                errors.append(f"{document_id}: {exc}")
                continue
            name = pdf_filename(court, document_id, decision)
            if name in used_names:
                name = f"{name.removesuffix('.pdf')}_{added}.pdf"
            used_names.add(name)
            archive.writestr(name, pdf)
            added += 1
            index_rows.append(_index_row(name, court, document_id, decision))

        archive.writestr("uebersicht.csv", _index_csv(index_rows))
        if errors:
            archive.writestr("fehler.txt", "\n".join(errors) + "\n")
        archive.writestr(
            "QUELLE.txt",
            f"{ATTRIBUTION}\nErstellt: {datetime.now(UTC).isoformat(timespec='seconds')}\n",
        )

    return ZipResult(content=buffer.getvalue(), added=added, errors=errors)


def _index_row(name: str, court: Court, document_id: str, decision: Decision | None) -> list[str]:
    if decision is None:
        return [name, court.value, document_id, "", "", "", "", "", ""]
    return [
        name,
        court.value,
        document_id,
        decision.doc_type.label,
        decision.case_number_display,
        decision.decision_date.isoformat() if decision.decision_date else "",
        decision.ecli or "",
        " | ".join(decision.norms),
        decision.ris_url or "",
    ]


def _index_csv(rows: list[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(
        [
            "Datei",
            "Gericht",
            "Dokumentnummer",
            "Typ",
            "Geschäftszahl",
            "Datum",
            "ECLI",
            "Normen",
            "RIS-Link",
        ]
    )
    writer.writerows(rows)
    return "\ufeff" + out.getvalue()  # BOM, damit Excel UTF-8 erkennt
