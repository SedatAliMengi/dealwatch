"""FastAPI dependencies: things endpoints ask for (DB session, price source)."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.sources import PriceSource


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_source(request: Request) -> PriceSource:
    return request.app.state.price_source
