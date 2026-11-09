"""Konfiguration der Anwendung.

Werte kommen aus Umgebungsvariablen mit dem Präfix ``JR_``. Die Umwandlung aus
den Strings der Umgebung geschieht hier explizit, weil das Modell im Pydantic
strict mode keine automatische Koerzierung (z. B. ``"2.0"`` → ``float``) erlaubt.
"""

import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

# Nutzungsbedingungen der RIS-OGD-Schnittstelle: höchstens 0,5 Anfragen pro Sekunde,
# keine parallelen Verbindungen. 2 Sekunden ist daher die Untergrenze.
MIN_ALLOWED_INTERVAL_SECONDS = 2.0


class Settings(BaseModel):
    """Laufzeit-Einstellungen."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    api_base_url: str = "https://data.bka.gv.at/ris/api/v2.6"
    document_base_url: str = "https://ogd.ris.bka.gv.at/Dokumente"
    user_agent: str = "judicataurus-rex/0.1"
    request_interval_seconds: float = Field(
        default=MIN_ALLOWED_INTERVAL_SECONDS, ge=MIN_ALLOWED_INTERVAL_SECONDS
    )
    timeout_seconds: float = Field(default=30.0, gt=0.0)
    max_documents_per_query: int = Field(default=1000, ge=100)
    max_zip_documents: int = Field(default=100, ge=1)
    cache_ttl_seconds: float = Field(default=3600.0, ge=0.0)
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Liest die Einstellungen aus der Umgebung; fehlende Werte nutzen den Default."""
        env: Mapping[str, str] = os.environ if environ is None else environ
        defaults = cls()

        def text(name: str, default: str) -> str:
            return env.get(f"JR_{name}", default)

        def number(name: str, default: float) -> float:
            raw = env.get(f"JR_{name}")
            return default if raw is None else float(raw)

        def integer(name: str, default: int) -> int:
            raw = env.get(f"JR_{name}")
            return default if raw is None else int(raw)

        return cls(
            api_base_url=text("API_BASE_URL", defaults.api_base_url),
            document_base_url=text("DOCUMENT_BASE_URL", defaults.document_base_url),
            user_agent=text("USER_AGENT", defaults.user_agent),
            request_interval_seconds=number(
                "REQUEST_INTERVAL_SECONDS", defaults.request_interval_seconds
            ),
            timeout_seconds=number("TIMEOUT_SECONDS", defaults.timeout_seconds),
            max_documents_per_query=integer(
                "MAX_DOCUMENTS_PER_QUERY", defaults.max_documents_per_query
            ),
            max_zip_documents=integer("MAX_ZIP_DOCUMENTS", defaults.max_zip_documents),
            cache_ttl_seconds=number("CACHE_TTL_SECONDS", defaults.cache_ttl_seconds),
            host=text("HOST", defaults.host),
            port=integer("PORT", defaults.port),
        )
