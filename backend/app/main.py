import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.ai.base import AIProvider
from app.ai.factory import build_provider
from app.api.routes import router
from app.config import Settings
from app.database.db import init_db, make_engine

ProviderFactory = Callable[[Settings], AIProvider | None]


def create_app(
    settings: Settings | None = None,
    provider_factory: ProviderFactory = build_provider,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        app.state.session_factory = init_db(engine, settings.questions_path)
        app.state.ai_provider = provider_factory(settings)
        yield
        if app.state.ai_provider is not None:
            app.state.ai_provider.close()
        engine.dispose()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title="SQL Mitra API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
