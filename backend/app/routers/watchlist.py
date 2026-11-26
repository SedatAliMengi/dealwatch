from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.deps import get_db, get_source
from app.models import WatchlistItem
from app.schemas import (
    ErrorOut,
    GameOut,
    PriceHistoryPoint,
    WatchlistCreate,
    WatchlistOut,
    WatchlistUpdate,
)
from app.services import watchlist
from app.sources import PriceSource

router = APIRouter(prefix="/watchlist", tags=["watchlist"])
NOT_FOUND = {404: {"model": ErrorOut}}

DB = Annotated[Session, Depends(get_db)]


def _to_out(item: WatchlistItem, latest: watchlist.LatestPrice | None) -> WatchlistOut:
    return WatchlistOut(
        id=item.id,
        game=GameOut.model_validate(item.game),
        target_price=item.target_price,
        latest_price=latest.price if latest else None,
        latest_store=latest.store_name if latest else None,
        latest_deal_url=latest.deal_url if latest else None,
        latest_checked_at=latest.checked_at if latest else None,
        below_target=bool(latest and latest.price < item.target_price),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _one(db: Session, item: WatchlistItem) -> WatchlistOut:
    return _to_out(item, watchlist.latest_prices(db, [item.game_id]).get(item.game_id))


@router.get("", response_model=list[WatchlistOut])
def list_watchlist(db: DB):
    """Every watched game with its target and latest best price."""
    items = watchlist.list_items(db)
    latest = watchlist.latest_prices(db, [i.game_id for i in items])
    return [_to_out(i, latest.get(i.game_id)) for i in items]


@router.post(
    "",
    response_model=WatchlistOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def add_to_watchlist(
    body: WatchlistCreate,
    db: DB,
    source: Annotated[PriceSource, Depends(get_source)],
):
    """Watch a game. Its current prices are saved immediately."""
    item = watchlist.add_item(db, source, body.external_id, body.target_price)
    return _one(db, item)


@router.get("/{item_id}", response_model=WatchlistOut, responses=NOT_FOUND)
def get_watchlist_item(item_id: int, db: DB):
    return _one(db, watchlist.get_item(db, item_id))


@router.patch("/{item_id}", response_model=WatchlistOut, responses=NOT_FOUND)
def update_watchlist_item(item_id: int, body: WatchlistUpdate, db: DB):
    """Change the target price."""
    return _one(db, watchlist.update_target(db, item_id, body.target_price))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def delete_watchlist_item(item_id: int, db: DB):
    """Stop watching a game (its alerts are removed too)."""
    watchlist.remove_item(db, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{item_id}/history", response_model=list[PriceHistoryPoint], responses=NOT_FOUND
)
def watchlist_price_history(
    item_id: int, db: DB, limit: Annotated[int, Query(ge=1, le=1000)] = 200
):
    """Best price at each check, oldest first. Feeds the chart."""
    return watchlist.price_history(db, item_id, limit)
