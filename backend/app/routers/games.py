from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.deps import get_source
from app.schemas import ErrorOut, GameOffersOut, GameSearchResult
from app.services import catalog
from app.sources import PriceSource

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/search", response_model=list[GameSearchResult])
def search_games(
    source: Annotated[PriceSource, Depends(get_source)],
    q: Annotated[str, Query(min_length=2, max_length=100, description="Part of a game title")],
    limit: Annotated[int, Query(ge=1, le=60)] = 10,
):
    """Search games by name. Shows the cheapest current price for each."""
    return [GameSearchResult(**vars(g)) for g in catalog.search_games(source, q, limit)]


@router.get(
    "/{external_id}/offers",
    response_model=GameOffersOut,
    responses={404: {"model": ErrorOut}},
)
def game_offers(
    source: Annotated[PriceSource, Depends(get_source)],
    external_id: Annotated[str, Path(min_length=1, max_length=100)],
):
    """Current price of one game in every store, cheapest first."""
    details = catalog.get_offers(source, external_id)
    return GameOffersOut(
        external_id=details.external_id,
        title=details.title,
        thumb_url=details.thumb_url,
        offers=[vars(o) for o in details.offers],
    )
