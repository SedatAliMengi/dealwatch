"""Live game search and current prices, straight from the price source."""

from app.services.errors import NotFoundError
from app.sources import GameDetails, GameSummary, PriceSource


def search_games(source: PriceSource, query: str, limit: int) -> list[GameSummary]:
    return source.search(query.strip(), limit=limit)


def get_offers(source: PriceSource, external_id: str) -> GameDetails:
    details = source.get_game(external_id)
    if details is None:
        raise NotFoundError(f"Game {external_id!r} not found at {source.name}")
    return details
