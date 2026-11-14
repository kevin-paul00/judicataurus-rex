"""Modelle für das JSON der Gegenstandsseiten (``/gegenstand/<GP>/<I|A>/<Nr>?json=true``)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RawModel(BaseModel):
    """Strict, unveränderlich; das Format ist nicht versioniert, daher ``extra="ignore"``."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")


class DocumentLink(RawModel):
    link: str
    type: str = ""


class DocumentGroup(RawModel):
    title: str = ""
    documents: list[DocumentLink] = Field(default_factory=list[DocumentLink])


class GegenstandContent(RawModel):
    title: str = ""
    zitation: str = ""
    description: str = ""
    documents: list[DocumentGroup] = Field(default_factory=list[DocumentGroup])


class GegenstandPage(RawModel):
    content: GegenstandContent


type MaterialsKind = Literal["RV", "IA"]


class Materials(BaseModel):
    """Die für die Anzeige benötigten Angaben zu einer Regierungsvorlage oder einem
    Initiativantrag.

    Beim Initiativantrag gibt es keine eigenen Erläuterungen: Das verlinkte Dokument ist
    der ganze Antrag, die Erläuterungen stehen darin unter „Begründung“.
    """

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    kind: MaterialsKind = "RV"
    legislative_period: str  # "XXVII"
    number: str  # "662" bzw. "2235"
    title: str
    citation: str  # "662 d.B." bzw. "2235/A"
    page_url: str
    explanations_html_url: str | None
    explanations_pdf_url: str | None
