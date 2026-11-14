"""FastAPI-Anwendung und Startpunkt."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from judicataurus_rex import __version__
from judicataurus_rex.config import Settings
from judicataurus_rex.parlament.client import ParlamentClient
from judicataurus_rex.ris.client import RisClient
from judicataurus_rex.ris.search import SearchService
from judicataurus_rex.statute import StatuteService
from judicataurus_rex.web.routes import Services, build_router


def create_app(
    settings: Settings | None = None,
    client: RisClient | None = None,
    parlament_client: ParlamentClient | None = None,
) -> FastAPI:
    """App-Factory. Die Clients lassen sich z. B. in Tests durch Mocks ersetzen."""
    resolved = settings or Settings.from_env()
    ris_client = client or RisClient(resolved)
    parlament = parlament_client or ParlamentClient(resolved)
    services = Services(
        settings=resolved,
        search=SearchService(ris_client, resolved),
        statute=StatuteService(ris_client, parlament, resolved),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        yield
        await ris_client.aclose()
        await parlament.aclose()

    app = FastAPI(title="Judicataurus Rex", version=__version__, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(build_router(services))
    return app


def run() -> None:
    """Konsolen-Einstiegspunkt: ``uv run judicataurus-rex``."""
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
