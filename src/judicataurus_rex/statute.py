"""Gesetzesansicht: Fassungen eines Paragraphen samt Parlamentsmaterialien.

Ablauf für eine gewählte Fassung:

1. RIS ``BrKons``: alle Fassungen des Paragraphen und der Text der gewählten Fassung
2. RIS ``BgblAuth``: zum ändernden Bundesgesetzblatt Gesetzgebungsperiode, Regierungsvorlage
   bzw. Initiativantrag, Ausschussbericht und Nationalratssitzung
3. Parlament: Erläuterungen der Regierungsvorlage, daraus die Abschnitte zum Paragraphen.
   Gibt es keine Regierungsvorlage, dient die Begründung des Initiativantrags als
   Erläuterungen.

Schritte 2 und 3 sind optional: Fehlt etwas oder schlägt ein Abruf fehl, gibt es einen
Hinweis, die Seite bleibt nutzbar.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

from judicataurus_rex.config import Settings
from judicataurus_rex.parlament.client import ParlamentClient, ParlamentError
from judicataurus_rex.parlament.erlaeuterungen import (
    ExplanationSection,
    extract_sections,
    justification_part,
)
from judicataurus_rex.parlament.models import Materials, MaterialsKind
from judicataurus_rex.ris import laws
from judicataurus_rex.ris.client import RisClient, RisError
from judicataurus_rex.ris.laws import LawAliases
from judicataurus_rex.ris.models import BgblInfo, LawVersion, NormQuery
from judicataurus_rex.text import Block, html_to_blocks, section

# Für Hinweise: „Zur Regierungsvorlage …“ / „Zum Initiativantrag …“.
_TO_SOURCE: dict[MaterialsKind, str] = {"RV": "Zur Regierungsvorlage", "IA": "Zum Initiativantrag"}


class StatuteError(ValueError):
    """Die Anfrage kann nicht beantwortet werden (unbekanntes Gesetz, keine Fassungen …)."""


@dataclass(frozen=True, slots=True)
class Link:
    label: str
    url: str


@dataclass(slots=True)
class MaterialsView:
    bgbl: str
    bgbl_info: BgblInfo | None = None
    materials: Materials | None = None
    other_links: list[Link] = field(default_factory=list[Link])
    sections: list[ExplanationSection] = field(default_factory=list[ExplanationSection])
    notes: list[str] = field(default_factory=list[str])


@dataclass(frozen=True, slots=True)
class StatuteView:
    law: LawAliases
    paragraph: str
    versions: tuple[LawVersion, ...]
    selected: LawVersion
    text: tuple[Block, ...]
    remarks: tuple[Block, ...]
    materials: MaterialsView | None
    warnings: tuple[str, ...]


class _TtlCache[K, V]:
    """Einfacher Cache mit Ablaufzeit; bei TTL 0 wird nichts gespeichert."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[K, tuple[float, V]] = {}

    async def get_or_load(self, key: K, load: Callable[[], Awaitable[V]]) -> V:
        now = time.monotonic()
        entry = self._entries.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]
        value = await load()
        if self._ttl > 0:
            self._entries[key] = (now + self._ttl, value)
        return value


def select_version(
    versions: tuple[LawVersion, ...],
    version_id: str | None,
    as_of: date | None,
    today: date,
) -> LawVersion:
    """Gewählte Fassung: per ID, sonst am Stichtag geltend, sonst heute geltend, sonst neueste."""
    if not versions:
        raise StatuteError("Keine Fassungen vorhanden.")
    if version_id is not None:
        for version in versions:
            if version.id == version_id:
                return version
    for day in (as_of, today):
        if day is None:
            continue
        valid = [v for v in versions if v.is_valid_on(day)]
        if valid:
            return valid[-1]
    return versions[-1]


class StatuteService:
    def __init__(self, ris: RisClient, parlament: ParlamentClient, settings: Settings) -> None:
        self._ris = ris
        self._parlament = parlament
        ttl = settings.law_cache_ttl_seconds
        self._versions: _TtlCache[tuple[str, str], tuple[LawVersion, ...]] = _TtlCache(ttl)
        self._bgbl: _TtlCache[str, BgblInfo | None] = _TtlCache(ttl)
        self._materials: _TtlCache[tuple[str, MaterialsKind, str], Materials] = _TtlCache(ttl)
        self._html: _TtlCache[str, tuple[Block, ...]] = _TtlCache(ttl)

    @property
    def parlament(self) -> ParlamentClient:
        return self._parlament

    async def view(
        self,
        norm: NormQuery,
        version_id: str | None = None,
        as_of: date | None = None,
        today: date | None = None,
    ) -> StatuteView:
        law = laws.lookup(norm.law)
        if law is None or law.gesetzesnummer is None:
            raise StatuteError(
                f"Für „{norm.law}“ ist noch keine Gesetzesansicht hinterlegt. Derzeit "
                "verfügbar: "
                + ", ".join(lw.canonical for lw in laws.KNOWN_LAWS if lw.gesetzesnummer)
                + ". Weitere Gesetze lassen sich in ris/laws.py ergänzen."
            )
        if norm.kind != "§" or norm.number is None:
            raise StatuteError(f"Bitte einen Paragraphen angeben, z. B. „{law.canonical} § 1“.")
        # Fassungen gibt es nur je Paragraph; Abs/Z der Eingabe werden ignoriert.
        gesetzesnummer, paragraph = law.gesetzesnummer, norm.number

        try:
            versions = await self._versions.get_or_load(
                (gesetzesnummer, paragraph),
                lambda: self._load_versions(gesetzesnummer, paragraph),
            )
        except RisError as exc:
            raise StatuteError(str(exc)) from exc
        if not versions:
            raise StatuteError(f"Im RIS gibt es keine Fassungen von {law.canonical} § {paragraph}.")

        selected = select_version(versions, version_id, as_of, today or date.today())
        warnings: list[str] = []
        if version_id is not None and selected.id != version_id:
            warnings.append("Die angefragte Fassung gibt es nicht; angezeigt wird eine andere.")

        text: tuple[Block, ...] = ()
        remarks: tuple[Block, ...] = ()
        if selected.html_url is not None:
            try:
                blocks = await self._html.get_or_load(
                    selected.html_url, lambda: self._ris_blocks(selected.html_url or "")
                )
            except (RisError, ValueError) as exc:
                warnings.append(f"Der Text dieser Fassung konnte nicht geladen werden: {exc}")
            else:
                text = tuple(section(list(blocks), "Text") or blocks)
                remarks = tuple(section(list(blocks), "Beachte") or ())

        materials = await self._materials_view(selected, law, paragraph)
        return StatuteView(
            law=law,
            paragraph=paragraph,
            versions=versions,
            selected=selected,
            text=text,
            remarks=remarks,
            materials=materials,
            warnings=tuple(warnings),
        )

    async def _load_versions(self, gesetzesnummer: str, paragraph: str) -> tuple[LawVersion, ...]:
        return tuple(await self._ris.law_versions(gesetzesnummer, paragraph))

    async def _ris_blocks(self, url: str) -> tuple[Block, ...]:
        return tuple(html_to_blocks(await self._ris.fetch_html(url)))

    async def _parlament_blocks(self, url: str) -> tuple[Block, ...]:
        return tuple(html_to_blocks(await self._parlament.fetch_html(url)))

    async def _materials_view(
        self, version: LawVersion, law: LawAliases, paragraph: str
    ) -> MaterialsView | None:
        bgbl = version.source_bgbl
        if bgbl is None:
            return None
        view = MaterialsView(bgbl=bgbl)

        try:
            info = await self._bgbl.get_or_load(bgbl, lambda: self._ris.bgbl_info(bgbl))
        except RisError as exc:
            view.notes.append(f"Die Daten zu {bgbl} konnten nicht geladen werden: {exc}")
            return view
        view.bgbl_info = info
        if info is None:
            view.notes.append(
                f"Zu {bgbl} gibt es im RIS keine Verweise auf die Parlamentsmaterialien "
                "(das authentische Bundesgesetzblatt gibt es erst ab 2004)."
            )
            return view

        period = info.legislative_period
        if period is None:
            view.notes.append(f"Zu {bgbl} ist keine Gesetzgebungsperiode angegeben.")
            return view
        for number in info.ab_numbers:
            self._add_link(view, f"Ausschussbericht {number} d.B. ({period}. GP)", period, number)
        for number in info.rv_numbers[1:]:
            self._add_link(view, f"Regierungsvorlage {number} d.B. ({period}. GP)", period, number)
        for number in info.ia_numbers[0 if info.rv_numbers else 1 :]:
            self._add_link(view, f"Initiativantrag {number}/A ({period}. GP)", period, number, "IA")

        # Erläuterungen: aus der Regierungsvorlage, sonst aus der Begründung des Initiativantrags.
        kind: MaterialsKind
        if info.rv_numbers:
            kind, number = "RV", info.rv_numbers[0]
        elif info.ia_numbers:
            kind, number = "IA", info.ia_numbers[0]
        else:
            view.notes.append(
                "Diesem Gesetz liegt weder eine Regierungsvorlage noch ein Initiativantrag "
                "zugrunde; Erläuterungen dazu stehen gegebenenfalls im Ausschussbericht."
            )
            return view
        try:
            materials = await self._materials.get_or_load(
                (period, kind, number), lambda: self._parlament.materials(period, number, kind)
            )
        except (ParlamentError, ValueError) as exc:
            view.notes.append(f"Die Materialien des Parlaments konnten nicht geladen werden: {exc}")
            return view
        view.materials = materials

        url = materials.explanations_html_url
        if url is None:
            view.notes.append(f"{_TO_SOURCE[kind]} gibt es keine Erläuterungen als HTML.")
            return view
        try:
            blocks = await self._html.get_or_load(url, lambda: self._parlament_blocks(url))
        except (ParlamentError, ValueError) as exc:
            view.notes.append(f"Die Erläuterungen konnten nicht geladen werden: {exc}")
            return view
        candidates = list(blocks)
        if kind == "IA":
            # Der Antrag enthält auch den Gesetzestext; erläutert wird erst in der Begründung.
            candidates = justification_part(candidates)
        view.sections = extract_sections(candidates, law, paragraph)
        if not view.sections:
            view.notes.append(
                f"In den Erläuterungen wurde kein eigener Abschnitt zu § {paragraph} gefunden. "
                "Bitte im vollständigen Dokument nachsehen."
            )
        return view

    def _add_link(
        self,
        view: MaterialsView,
        label: str,
        period: str,
        number: str,
        kind: MaterialsKind = "RV",
    ) -> None:
        try:
            url = self._parlament.gegenstand_url(period, number, kind)
            view.other_links.append(Link(label, url))
        except ValueError:
            return
