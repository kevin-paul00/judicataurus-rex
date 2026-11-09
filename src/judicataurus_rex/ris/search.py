"""Suche nach Judikatur zu einer oder mehreren Normen.

* **ODER**: Für jede Kombination aus Norm, Gericht und Zitierweise werden alle Seiten geladen, die
  Ergebnisse werden vereinigt.
* **UND**: Je Gericht wird für jede Norm nur die erste Seite geladen. Das liefert
  die Trefferzahlen. Danach wird nur die Norm mit den wenigsten Treffern vollständig
  geladen und lokal auf alle übrigen Normen gefiltert. Das spart Anfragen, die bei
  0,5 Anfragen/s teuer sind.

In beiden Fällen prüft :func:`normalize.matches` jedes Dokument lokal gegen die
Norm (inkl. Abs/Z). So fallen ungenaue Treffer der RIS-Suche weg (etwa § 63a statt § 63).
"""

import math
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from judicataurus_rex.config import Settings
from judicataurus_rex.ris.client import PAGE_SIZE, Page, RisClient
from judicataurus_rex.ris.models import Court, Decision, NormQuery, SearchRequest, SearchResult
from judicataurus_rex.ris.normalize import api_terms, matches

type _CacheKey = tuple[Court, str, int, date | None, date | None]


@dataclass(slots=True)
class _Fetched:
    """Alle geladenen Dokumente einer Norm bei einem Gericht."""

    decisions: dict[str, Decision] = field(default_factory=dict[str, Decision])
    total: int = 0
    truncated: bool = False


@dataclass(slots=True)
class _Stats:
    requests: int = 0
    rejected: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list[str])


class SearchService:
    """Führt Suchen aus, cached Ergebnisseiten und merkt sich gefundene Dokumente."""

    def __init__(self, client: RisClient, settings: Settings) -> None:
        self._client = client
        self._ttl = settings.cache_ttl_seconds
        self._max_pages = max(1, math.ceil(settings.max_documents_per_query / PAGE_SIZE))
        self._cache: dict[_CacheKey, tuple[float, Page]] = {}
        self._known: dict[str, Decision] = {}

    @property
    def client(self) -> RisClient:
        return self._client

    def known_decision(self, document_id: str) -> Decision | None:
        """Ein Dokument aus einer früheren Suche (für Dateinamen im ZIP)."""
        return self._known.get(document_id)

    async def search(self, request: SearchRequest) -> SearchResult:
        stats = _Stats()
        found: dict[str, Decision] = {}
        for court in request.courts:
            if request.mode == "and":
                court_hits = await self._search_and(court, request, stats)
            else:
                court_hits = await self._search_or(court, request, stats)
            found.update(court_hits)

        wanted = set(request.doc_types)
        decisions = sorted(
            (d for d in found.values() if d.doc_type in wanted),
            key=lambda d: (d.decision_date or date.min, d.id),
            reverse=True,
        )
        self._known.update((d.id, d) for d in decisions)

        if stats.rejected:
            stats.warnings.append(
                f"{stats.rejected} Treffer der RIS-Suche wurden verworfen, weil keine ihrer "
                "Normen exakt zur Anfrage passt (z. B. anderer Absatz oder § 63a statt § 63)."
            )
        return SearchResult(
            decisions=tuple(decisions),
            warnings=tuple(stats.warnings),
            request_count=stats.requests,
            truncated=stats.truncated,
        )

    async def _search_or(
        self, court: Court, request: SearchRequest, stats: _Stats
    ) -> dict[str, Decision]:
        result: dict[str, Decision] = {}
        for norm in request.norms:
            fetched = await self._fetch_norm(court, norm, request, stats, first_page_only=False)
            result.update(self._filter(fetched.decisions.values(), (norm,), stats))
        return result

    async def _search_and(
        self, court: Court, request: SearchRequest, stats: _Stats
    ) -> dict[str, Decision]:
        probes: list[tuple[NormQuery, _Fetched]] = []
        for norm in request.norms:
            probe = await self._fetch_norm(court, norm, request, stats, first_page_only=True)
            if probe.total == 0:
                return {}
            probes.append((norm, probe))

        narrowest, _ = min(probes, key=lambda item: item[1].total)
        fetched = await self._fetch_norm(court, narrowest, request, stats, first_page_only=False)
        candidates = self._filter(fetched.decisions.values(), (narrowest,), stats)
        return {
            doc_id: decision
            for doc_id, decision in candidates.items()
            if all(matches(norm, decision.norms) for norm in request.norms)
        }

    def _filter(
        self, decisions: Iterable[Decision], norms: tuple[NormQuery, ...], stats: _Stats
    ) -> dict[str, Decision]:
        accepted: dict[str, Decision] = {}
        for decision in decisions:
            if all(matches(norm, decision.norms) for norm in norms):
                accepted[decision.id] = decision
            else:
                stats.rejected += 1
        return accepted

    async def _fetch_norm(
        self,
        court: Court,
        norm: NormQuery,
        request: SearchRequest,
        stats: _Stats,
        *,
        first_page_only: bool,
    ) -> _Fetched:
        fetched = _Fetched()
        for term in api_terms(norm, court):
            first = await self._page(court, term, 1, request, stats)
            fetched.total += first.total
            fetched.decisions.update((d.id, d) for d in first.decisions)
            if first_page_only:
                continue

            pages_needed = math.ceil(first.total / PAGE_SIZE)
            last_page = min(pages_needed, self._max_pages)
            if pages_needed > self._max_pages:
                fetched.truncated = True
                stats.truncated = True
                stats.warnings.append(
                    f"„{term}“ ({court.label}): {first.total} Treffer, geladen wurden nur die "
                    f"neuesten {last_page * PAGE_SIZE}. Bitte die Suche eingrenzen "
                    "(Absatz angeben oder Datumsbereich setzen)."
                )
            for page_number in range(2, last_page + 1):
                page = await self._page(court, term, page_number, request, stats)
                fetched.decisions.update((d.id, d) for d in page.decisions)
                if not page.decisions:
                    break
        return fetched

    async def _page(
        self, court: Court, term: str, page_number: int, request: SearchRequest, stats: _Stats
    ) -> Page:
        key: _CacheKey = (court, term, page_number, request.date_from, request.date_to)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        page = await self._client.search_page(
            court, term, page_number, request.date_from, request.date_to
        )
        stats.requests += 1
        self._cache[key] = (now + self._ttl, page)
        return page
