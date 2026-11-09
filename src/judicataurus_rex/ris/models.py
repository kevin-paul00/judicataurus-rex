"""Domänenmodelle der Anwendung (unabhängig vom RIS-Rohformat)."""

import re
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Dokumentnummern im RIS, z. B. "BVWGT_20260831_W129_2323711_1_00" oder "JFR_20211216_21G00224_01".
DOCUMENT_ID_PATTERN = re.compile(r"^[A-Z0-9_]{5,80}$")


class Court(StrEnum):
    """RIS-Judikatur-Applikationen. Der Wert ist der ``Applikation``-Parameter."""

    BVWG = "Bvwg"
    VWGH = "Vwgh"
    VFGH = "Vfgh"
    JUSTIZ = "Justiz"
    LVWG = "Lvwg"
    DSK = "Dsk"

    @property
    def label(self) -> str:
        return _COURT_LABELS[self]


_COURT_LABELS: dict[Court, str] = {
    Court.BVWG: "Bundesverwaltungsgericht (BVwG)",
    Court.VWGH: "Verwaltungsgerichtshof (VwGH)",
    Court.VFGH: "Verfassungsgerichtshof (VfGH)",
    Court.JUSTIZ: "Justiz (OGH, OLG, LG)",
    Court.LVWG: "Landesverwaltungsgerichte (LVwG)",
    Court.DSK: "Datenschutzbehörde / Datenschutzkommission (DSB)",
}

# Standardauswahl: Fokus Hochschulrecht (BVwG), ergänzt um die Höchstgerichte.
DEFAULT_COURTS: tuple[Court, ...] = (Court.BVWG, Court.VWGH, Court.VFGH)


class DocType(StrEnum):
    """Dokumenttyp im RIS (Feld ``Judikatur.Dokumenttyp``)."""

    RECHTSSATZ = "Rechtssatz"
    TEXT = "Text"

    @property
    def label(self) -> str:
        return "Rechtssatz" if self is DocType.RECHTSSATZ else "Entscheidungstext"


type SearchMode = Literal["and", "or"]
type NormKind = Literal["§", "Art"]


class DomainModel(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class NormQuery(DomainModel):
    """Eine vom Benutzer eingegebene Norm, z. B. ``§ 63 Abs 1 UG``."""

    raw: str
    law: str
    kind: NormKind | None = None
    number: str | None = None
    # Untergliederung als (Art, Wert)-Paare, z. B. (("abs", "1"), ("z", "3")).
    subdivisions: tuple[tuple[str, str], ...] = ()

    @property
    def display(self) -> str:
        parts = [self.law]
        if self.kind is not None and self.number is not None:
            parts.append(f"{self.kind} {self.number}")
        parts.extend(f"{name.capitalize()} {value}" for name, value in self.subdivisions)
        return " ".join(parts)


class Decision(DomainModel):
    """Ein Judikaturdokument (Rechtssatz oder Entscheidungstext)."""

    id: str = Field(pattern=DOCUMENT_ID_PATTERN.pattern)
    court: Court
    organ: str
    doc_type: DocType
    case_numbers: tuple[str, ...]
    decision_date: date | None
    norms: tuple[str, ...]
    ecli: str | None
    keywords: str | None
    ris_url: str | None
    pdf_url: str | None

    @property
    def case_number_display(self) -> str:
        return "; ".join(self.case_numbers) if self.case_numbers else self.id


class SearchRequest(DomainModel):
    norms: tuple[NormQuery, ...] = Field(min_length=1)
    courts: tuple[Court, ...] = Field(min_length=1)
    mode: SearchMode = "or"
    doc_types: tuple[DocType, ...] = (DocType.TEXT, DocType.RECHTSSATZ)
    date_from: date | None = None
    date_to: date | None = None


class SearchResult(DomainModel):
    decisions: tuple[Decision, ...]
    warnings: tuple[str, ...] = ()
    request_count: int = 0
    truncated: bool = False
