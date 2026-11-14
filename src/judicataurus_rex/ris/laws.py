"""Alias-Tabelle für Gesetzesbezeichnungen.

Die Gerichte zitieren dasselbe Gesetz im RIS-Feld ``Normen`` unterschiedlich. Gegen
die Live-API geprüft (2026-11):

* Universitätsgesetz 2002: BVwG ``UG``; VwGH und VfGH ``UniversitätsG 2002``
* HSG 2014: BVwG und VwGH ``HSG 2014``;
  VfGH ``Hochschülerinnen- und HochschülerschaftsG 2014``

Unbekannte Gesetze werden unverändert an die API übergeben. Weitere Einträge
können in :data:`KNOWN_LAWS` ergänzt werden.

Für die Gesetzesansicht (Fassungen und Erläuterungen) braucht ein Eintrag zusätzlich
die ``gesetzesnummer`` aus dem RIS (steht in der URL der geltenden Fassung, z. B.
``…Gesetzesnummer=20002128``) und den ``full_title``, wie er in den Erläuterungen
der Regierungsvorlagen steht (z. B. „Universitätsgesetz 2002“).
"""

from pydantic import BaseModel, ConfigDict, Field

from judicataurus_rex.ris.models import Court


class LawAliases(BaseModel):
    """Bezeichnungen eines Gesetzes, insgesamt und je Gericht."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    canonical: str
    # Amtlicher Titel, wie er in den Erläuterungen („Änderung des …“) vorkommt.
    full_title: str
    # Gesetzesnummer im RIS (Bundesrecht konsolidiert); None = keine Gesetzesansicht.
    gesetzesnummer: str | None = None
    # Alles, was ein Benutzer eingeben könnte (Vergleich ohne Groß-/Kleinschreibung).
    names: tuple[str, ...]
    # Zitierweise je Gericht. Gerichte ohne Eintrag bekommen alle Werte aus ``fallback``.
    per_court: dict[Court, tuple[str, ...]] = Field(default_factory=dict[Court, tuple[str, ...]])
    fallback: tuple[str, ...]

    def citations_for(self, court: Court) -> tuple[str, ...]:
        return self.per_court.get(court, self.fallback)

    @property
    def all_citations(self) -> frozenset[str]:
        values = set(self.names) | set(self.fallback)
        for citations in self.per_court.values():
            values.update(citations)
        return frozenset(values)


KNOWN_LAWS: tuple[LawAliases, ...] = (
    LawAliases(
        canonical="UG",
        full_title="Universitätsgesetz 2002",
        gesetzesnummer="20002128",
        names=(
            "UG",
            "UG 2002",
            "UniversitätsG 2002",
            "Universitätsgesetz 2002",
            "Universitätsgesetz",
        ),
        per_court={
            Court.BVWG: ("UG",),
            Court.VWGH: ("UniversitätsG 2002",),
            Court.VFGH: ("UniversitätsG 2002",),
        },
        fallback=("UG", "UniversitätsG 2002"),
    ),
    LawAliases(
        canonical="HSG 2014",
        full_title="Hochschülerinnen- und Hochschülerschaftsgesetz 2014",
        gesetzesnummer="20008892",
        names=(
            "HSG",
            "HSG 2014",
            "Hochschülerinnen- und HochschülerschaftsG 2014",
            "Hochschülerinnen- und Hochschülerschaftsgesetz 2014",
        ),
        per_court={
            Court.BVWG: ("HSG 2014",),
            Court.VWGH: ("HSG 2014",),
            Court.VFGH: ("Hochschülerinnen- und HochschülerschaftsG 2014",),
        },
        fallback=("HSG 2014", "Hochschülerinnen- und HochschülerschaftsG 2014"),
    ),
)


def _key(name: str) -> str:
    return " ".join(name.split()).casefold()


_BY_NAME: dict[str, LawAliases] = {_key(n): law for law in KNOWN_LAWS for n in law.names}


def lookup(law: str) -> LawAliases | None:
    return _BY_NAME.get(_key(law))


def citations_for(law: str, court: Court) -> tuple[str, ...]:
    """Zitierweisen, mit denen ``law`` bei ``court`` gesucht werden muss."""
    known = lookup(law)
    return known.citations_for(court) if known is not None else (law,)


def matching_names(law: str) -> frozenset[str]:
    """Alle Bezeichnungen (casefolded), die beim lokalen Abgleich als ``law`` gelten."""
    known = lookup(law)
    names = known.all_citations if known is not None else frozenset({law})
    return frozenset(_key(n) for n in names)


def normalize_name(name: str) -> str:
    """Vergleichsschlüssel für eine Gesetzesbezeichnung."""
    return _key(name)
