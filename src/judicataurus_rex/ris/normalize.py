"""Normen parsen, in die RIS-Abfragesyntax übersetzen und lokal abgleichen.

Unterstützte Eingaben (Groß-/Kleinschreibung und Leerzeichen egal):

* ``UG § 63``, ``UG §63 Abs 1 Z 3``, ``HSG 2014 § 31``
* ``§ 63 UG``, ``§ 63 Abs. 1 UG``
* ``B-VG Art 133``, ``Art. 133 Abs 4 B-VG``
* nur ein Gesetz: ``HSG 2014`` (alle Paragraphen)

Die RIS-Daten speichern Normen als ``"<Gesetz> §<Nr> [Abs<n>] [Z<n>] …"``,
z. B. ``UG §63 Abs1 Z3`` oder ``B-VG Art133 Abs4``.
"""

import re
from dataclasses import dataclass

from judicataurus_rex.ris import laws
from judicataurus_rex.ris.models import Court, NormKind, NormQuery

_KIND = r"(?P<kind>§+|Art\.?)"
_NUMBER = r"(?P<number>\d+[a-z]*)"

# "<Gesetz> § <Nr> <Rest>" oder nur "<Gesetz>"
_LAW_FIRST = re.compile(rf"^(?P<law>.+?)(?:\s*{_KIND}\s*{_NUMBER}(?P<rest>.*))?$", re.IGNORECASE)
# "§ <Nr> <Untergliederung> <Gesetz>"
_KIND_FIRST = re.compile(rf"^{_KIND}\s*{_NUMBER}(?P<rest>.*)$", re.IGNORECASE)
# Eine Untergliederung, z. B. "Abs 1", "Abs. 10a", "Z3", "lit a"
_SUBDIVISION = re.compile(
    r"\s*(?P<name>UAbs|Abs|Satz|lit|Z)\.?\s*(?P<value>\d+[a-z]?|[a-z])(?=\s|$|[;,.])",
    re.IGNORECASE,
)


class NormParseError(ValueError):
    """Die Eingabe ist keine erkennbare Norm."""


@dataclass(frozen=True, slots=True)
class ParsedNorm:
    """Eine zerlegte Norm, aus der Benutzereingabe oder aus den RIS-Daten."""

    law: str
    kind: NormKind | None
    number: str | None
    subdivisions: tuple[tuple[str, str], ...]
    tail: str


def _clean(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split()).strip(" ;,")


def _kind(raw: str | None) -> NormKind | None:
    if raw is None:
        return None
    return "§" if raw.startswith("§") else "Art"


def _subdivisions(text: str) -> tuple[tuple[tuple[str, str], ...], str]:
    """Liest Untergliederungen vom Anfang von ``text``; gibt (Tupel, Resttext) zurück."""
    found: list[tuple[str, str]] = []
    pos = 0
    while (match := _SUBDIVISION.match(text, pos)) is not None:
        found.append((match.group("name").casefold(), match.group("value").casefold()))
        pos = match.end()
    return tuple(found), text[pos:].strip(" .;,")


def parse(text: str) -> ParsedNorm:
    """Zerlegt eine Norm. Wirft :class:`NormParseError` bei leerer oder unklarer Eingabe."""
    cleaned = _clean(text)
    if not cleaned:
        raise NormParseError("Leere Norm.")

    if (match := _KIND_FIRST.match(cleaned)) is not None:
        subdivisions, law = _subdivisions(match.group("rest"))
        if not law:
            raise NormParseError(f"Gesetz fehlt in „{cleaned}“ (z. B. „§ 63 UG“).")
        return ParsedNorm(
            law=law,
            kind=_kind(match.group("kind")),
            number=match.group("number"),
            subdivisions=subdivisions,
            tail="",
        )

    match = _LAW_FIRST.match(cleaned)
    if match is None:  # pragma: no cover - das Muster passt auf jeden nicht-leeren String
        raise NormParseError(f"Unbekanntes Normformat: „{cleaned}“.")
    rest = match.group("rest") or ""
    subdivisions, tail = _subdivisions(rest)
    return ParsedNorm(
        law=match.group("law").strip(),
        kind=_kind(match.group("kind")),
        number=match.group("number"),
        subdivisions=subdivisions,
        tail=tail,
    )


def parse_query(text: str) -> NormQuery:
    """Benutzereingabe → :class:`NormQuery`."""
    parsed = parse(text)
    if parsed.tail:
        raise NormParseError(
            f"Nicht verstanden: „{parsed.tail}“ in „{_clean(text)}“. "
            "Erlaubt sind z. B. „UG § 63 Abs 1 Z 3“ oder „§ 63 UG“."
        )
    return NormQuery(
        raw=_clean(text),
        law=parsed.law,
        kind=parsed.kind,
        number=parsed.number,
        subdivisions=parsed.subdivisions,
    )


def parse_queries(text: str) -> tuple[list[NormQuery], list[str]]:
    """Mehrzeilige Eingabe (eine Norm pro Zeile) → (gültige Normen, Fehlermeldungen)."""
    queries: list[NormQuery] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            query = parse_query(line)
        except NormParseError as exc:
            errors.append(str(exc))
            continue
        key = query.display.casefold()
        if key not in seen:
            seen.add(key)
            queries.append(query)
    return queries, errors


def api_terms(query: NormQuery, court: Court) -> tuple[str, ...]:
    """Werte für den ``Norm``-Parameter der RIS-API.

    Untergliederungen (Abs, Z …) werden nicht mitgeschickt, sondern lokal über
    :func:`matches` gefiltert, weil die RIS-Volltextsuche sie unzuverlässig behandelt.
    """
    citations = laws.citations_for(query.law, court)
    if query.kind is None or query.number is None:
        return citations
    # Live geprüft: "UG § 63" findet Treffer, Artikel nur in der Form "B-VG Art133".
    if query.kind == "§":
        return tuple(f"{citation} § {query.number}" for citation in citations)
    return tuple(f"{citation} Art{query.number}" for citation in citations)


_LIST_ITEM = re.compile(r"^\s*(?:§|Art\.?\s*\d)", re.IGNORECASE)


def expand(raw: str) -> list[ParsedNorm]:
    """Zerlegt einen RIS-Normeintrag, der auch mehrere Fundstellen enthalten kann.

    Der VfGH bündelt etwa ``UniversitätsG 2002 §51 Abs2, §63 Abs1, §64`` oder
    ``B-VG Art132, Art133`` in einem Eintrag.
    """
    first, *others = raw.split(",")
    try:
        head = parse(first)
    except NormParseError:
        return []
    result = [head]
    for other in others:
        if _LIST_ITEM.match(other) is None:
            continue
        try:
            result.append(parse(f"{head.law} {other.strip()}"))
        except NormParseError:
            continue
    return result


def matches(query: NormQuery, document_norms: tuple[str, ...]) -> bool:
    """Prüft, ob eine der Normen eines Dokuments die Anfrage exakt erfüllt."""
    law_names = laws.matching_names(query.law)
    candidates = (parsed for raw in document_norms for parsed in expand(raw))
    for parsed in candidates:
        if laws.normalize_name(parsed.law) not in law_names:
            continue
        if query.number is None:
            return True
        if parsed.kind != query.kind or parsed.number is None:
            continue
        if parsed.number.casefold() != query.number.casefold():
            continue
        if parsed.subdivisions[: len(query.subdivisions)] == query.subdivisions:
            return True
    return False
