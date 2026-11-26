"""Builds the FastAPI app. Run with:

    uvicorn app.main:create_app --factory
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.routers import alerts, games, system, watchlist
from app.scheduler import build_scheduler
from app.services.errors import ConflictError, NotFoundError
from app.sources import PriceSource, PriceSourceError
from app.sources.registry import create_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
    source: PriceSource | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    session_factory = session_factory or make_session_factory(make_engine(settings.database_url))
    source = source or create_source(settings.price_source, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if settings.scheduler_enabled:
            scheduler = build_scheduler(settings, session_factory, source)
            scheduler.start()
        app.state.scheduler = scheduler
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(
        title="Dealwatch API",
        version="1.0.0",
        description="Game price alerts. Price data by CheapShark (https://www.cheapshark.com).",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.price_source = source

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError):
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(PriceSourceError)
    async def _source_down(_: Request, exc: PriceSourceError):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": f"Price source error: {exc}"},
        )

    for router in (system.router, games.router, watchlist.router, alerts.router):
        app.include_router(router, prefix="/api")
    return app
