"""Pydantic-Modelle für die rohe JSON-Antwort von ``GET /Judikatur``.

Die RIS-Antwort ist aus XML nach JSON konvertiert. Daraus folgen einige Eigenheiten:

* Ein Element mit genau einem Kind erscheint als Skalar oder Objekt, mit mehreren
  Kindern als Liste (``item``, ``ContentReference``, ``OgdDocumentReference`` …).
* Leere Elemente erscheinen als ``{"@xsi:nil": "true", ...}``.
* Alle Werte, auch Zahlen und Datumsangaben, sind Strings.

Die Modelle sind strict. Sie vereinheitlichen deshalb nur Skalar und Liste und
wandeln keine Typen um. Die fachliche Umwandlung steht in :mod:`.mapping`.
"""

from typing import Annotated, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _as_list(value: object) -> object:
    """Skalar → einelementige Liste, ``None``/nil-Objekt → leere Liste."""
    if value is None:
        return []
    if isinstance(value, list):
        return cast(list[object], value)
    if isinstance(value, dict) and "@xsi:nil" in cast(dict[str, object], value):
        return []
    result: list[object] = [value]
    return result


def _as_str_list(value: object) -> object:
    """Wie :func:`_as_list`, verwirft aber alles, was kein String ist."""
    items = _as_list(value)
    if isinstance(items, list):
        return [item for item in cast(list[object], items) if isinstance(item, str)]
    return items


def _optional_str(value: object) -> object:
    """Nicht-String-Werte (z. B. nil-Objekte) → ``None``."""
    return value if isinstance(value, str) else None


type StrList = Annotated[list[str], BeforeValidator(_as_str_list)]
type OptStr = Annotated[str | None, BeforeValidator(_optional_str)]


class RawModel(BaseModel):
    """Basis: strict, unveränderlich, unbekannte Felder werden ignoriert."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")


class ItemList(RawModel):
    item: StrList = Field(default_factory=list[str])


class ContentUrl(RawModel):
    data_type: str = Field(alias="DataType")
    url: str = Field(alias="Url")


class Urls(RawModel):
    content_url: Annotated[list[ContentUrl], BeforeValidator(_as_list)] = Field(
        default_factory=list[ContentUrl], alias="ContentUrl"
    )


class ContentReference(RawModel):
    content_type: OptStr = Field(default=None, alias="ContentType")
    name: OptStr = Field(default=None, alias="Name")
    urls: Urls = Field(default_factory=Urls, alias="Urls")


class Dokumentliste(RawModel):
    content_reference: Annotated[list[ContentReference], BeforeValidator(_as_list)] = Field(
        default_factory=list[ContentReference], alias="ContentReference"
    )


class Technisch(RawModel):
    id: str = Field(alias="ID")
    applikation: str = Field(alias="Applikation")
    organ: OptStr = Field(default=None, alias="Organ")


class Allgemein(RawModel):
    dokument_url: OptStr = Field(default=None, alias="DokumentUrl")
    veroeffentlicht: OptStr = Field(default=None, alias="Veroeffentlicht")
    geaendert: OptStr = Field(default=None, alias="Geaendert")


class JudikaturMeta(RawModel):
    dokumenttyp: OptStr = Field(default=None, alias="Dokumenttyp")
    geschaeftszahl: ItemList = Field(default_factory=ItemList, alias="Geschaeftszahl")
    normen: ItemList = Field(default_factory=ItemList, alias="Normen")
    entscheidungsdatum: OptStr = Field(default=None, alias="Entscheidungsdatum")
    schlagworte: OptStr = Field(default=None, alias="Schlagworte")
    ecli: OptStr = Field(default=None, alias="EuropeanCaseLawIdentifier")
    gesamte_entscheidung_url: OptStr = Field(default=None, alias="GesamteEntscheidungUrl")


class Metadaten(RawModel):
    technisch: Technisch = Field(alias="Technisch")
    allgemein: Allgemein = Field(default_factory=Allgemein, alias="Allgemein")
    judikatur: JudikaturMeta = Field(default_factory=JudikaturMeta, alias="Judikatur")


class Data(RawModel):
    metadaten: Metadaten = Field(alias="Metadaten")
    dokumentliste: Dokumentliste = Field(default_factory=Dokumentliste, alias="Dokumentliste")


class DocumentReference(RawModel):
    data: Data = Field(alias="Data")


class Hits(RawModel):
    page_number: str = Field(alias="@pageNumber")
    page_size: str = Field(alias="@pageSize")
    total: str = Field(alias="#text")


class DocumentResults(RawModel):
    hits: Hits = Field(alias="Hits")
    references: Annotated[list[DocumentReference], BeforeValidator(_as_list)] = Field(
        default_factory=list[DocumentReference], alias="OgdDocumentReference"
    )


class RisErrorPayload(RawModel):
    applikation: OptStr = Field(default=None, alias="Applikation")
    message: str = Field(alias="Message")


class SearchResultBody(RawModel):
    results: DocumentResults | None = Field(default=None, alias="OgdDocumentResults")
    error: RisErrorPayload | None = Field(default=None, alias="Error")


class Envelope(RawModel):
    """Wurzelobjekt der Antwort: ``{"OgdSearchResult": {...}}``."""

    body: SearchResultBody = Field(alias="OgdSearchResult")
