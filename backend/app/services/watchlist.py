"""Watchlist: add a game with a target price, list, update, remove, history."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Game, PricePoint, WatchlistItem, utcnow
from app.services.errors import ConflictError, NotFoundError
from app.services.price_checker import record_check
from app.sources import PriceSource


@dataclass
class LatestPrice:
    price: Decimal
    store_name: str
    deal_url: str | None
    checked_at: datetime


@dataclass
class HistoryPoint:
    checked_at: datetime
    price: Decimal
    store_name: str


def list_items(db: Session) -> list[WatchlistItem]:
    return list(
        db.scalars(
            select(WatchlistItem)
            .options(joinedload(WatchlistItem.game))
            .order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
        )
    )


def get_item(db: Session, item_id: int) -> WatchlistItem:
    item = db.get(WatchlistItem, item_id, options=[joinedload(WatchlistItem.game)])
    if item is None:
        raise NotFoundError(f"Watchlist item {item_id} not found")
    return item


def add_item(
    db: Session, source: PriceSource, external_id: str, target_price: Decimal
) -> WatchlistItem:
    game = db.scalar(
        select(Game).where(Game.source == source.name, Game.external_id == external_id)
    )
    if game is not None and game.watch is not None:
        raise ConflictError(f"{game.title!r} is already on your watchlist")

    details = source.get_game(external_id)
    if details is None:
        raise NotFoundError(f"Game {external_id!r} not found at {source.name}")

    if game is None:
        game = Game(source=source.name, external_id=external_id, title=details.title)
        db.add(game)
    item = WatchlistItem(game=game, target_price=target_price)
    db.add(item)
    db.flush()

    # Save today's prices right away (first history point, maybe an alert).
    record_check(db, item, details, utcnow())
    db.commit()
    return item


def update_target(db: Session, item_id: int, target_price: Decimal) -> WatchlistItem:
    item = get_item(db, item_id)
    item.target_price = target_price
    item.last_alerted_price = None  # new target: allow a fresh alert
    db.commit()
    return item


def remove_item(db: Session, item_id: int) -> None:
    item = get_item(db, item_id)
    db.delete(item)
    db.commit()


def latest_prices(db: Session, game_ids: list[int]) -> dict[int, LatestPrice]:
    """Best (lowest) price from the most recent check of each game."""
    if not game_ids:
        return {}
    newest = (
        select(PricePoint.game_id, func.max(PricePoint.checked_at).label("latest"))
        .where(PricePoint.game_id.in_(game_ids))
        .group_by(PricePoint.game_id)
        .subquery()
    )
    rows = db.scalars(
        select(PricePoint)
        .join(
            newest,
            (PricePoint.game_id == newest.c.game_id)
            & (PricePoint.checked_at == newest.c.latest),
        )
        .order_by(PricePoint.price)
    )
    result: dict[int, LatestPrice] = {}
    for p in rows:
        result.setdefault(
            p.game_id, LatestPrice(p.price, p.store_name, p.deal_url, p.checked_at)
        )
    return result


def price_history(db: Session, item_id: int, limit: int = 200) -> list[HistoryPoint]:
    """Best price per check, oldest first (ready for a line chart)."""
    item = get_item(db, item_id)
    rows = db.scalars(
        select(PricePoint)
        .where(PricePoint.game_id == item.game_id)
        .order_by(PricePoint.checked_at, PricePoint.price)
    )
    best_per_check: dict[datetime, HistoryPoint] = {}
    for p in rows:
        best_per_check.setdefault(p.checked_at, HistoryPoint(p.checked_at, p.price, p.store_name))
    points = list(best_per_check.values())
    return points[-limit:]
