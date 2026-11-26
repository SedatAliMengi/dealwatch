"""The price checker: fetch prices, save history, create alerts.

Runs on a schedule (see app/scheduler.py) and on demand (POST /api/checker/run).

Alert rule (no duplicates):
  * best price >= target          -> no alert; also "re-arm" the item
                                     (forget the last alerted price)
  * best price <  target, and
      - never alerted (since re-arm) -> ALERT
      - lower than last alerted      -> ALERT (it dropped even further)
      - same or higher than last     -> no alert (we already told you)
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Alert, Game, PricePoint, WatchlistItem, utcnow
from app.services.errors import ConflictError
from app.sources import GameDetails, Offer, PriceSource, PriceSourceError

log = logging.getLogger(__name__)

# Only one check at a time (scheduler + manual trigger could overlap).
_run_lock = threading.Lock()


class CheckAlreadyRunning(ConflictError):
    pass


@dataclass
class CheckResult:
    checked: int = 0
    prices_saved: int = 0
    alerts_created: int = 0
    errors: list[str] = field(default_factory=list)


def decide_alert(item: WatchlistItem, best: Offer) -> Alert | None:
    """Pure decision logic. Updates item.last_alerted_price as a side effect."""
    if best.price >= item.target_price:
        item.last_alerted_price = None  # price recovered: next drop alerts again
        return None
    if item.last_alerted_price is not None and best.price >= item.last_alerted_price:
        return None  # already alerted at this price (or a lower one)
    item.last_alerted_price = best.price
    return Alert(
        item=item,
        price=best.price,
        target_price=item.target_price,
        store_name=best.store_name,
        deal_url=best.deal_url,
    )


def record_check(
    db: Session, item: WatchlistItem, details: GameDetails, checked_at: datetime
) -> tuple[int, Alert | None]:
    """Save one game's offers as history and maybe create an alert.

    Returns (number of price points saved, alert or None). Does not commit.
    """
    item.game.title = details.title
    if details.thumb_url:
        item.game.thumb_url = details.thumb_url
    for offer in details.offers:
        db.add(
            PricePoint(
                game_id=item.game_id,
                store_id=offer.store_id,
                store_name=offer.store_name,
                price=offer.price,
                regular_price=offer.regular_price,
                deal_url=offer.deal_url,
                checked_at=checked_at,
            )
        )
    best = details.best_offer
    alert = decide_alert(item, best) if best is not None else None
    if alert is not None:
        db.add(alert)
    return len(details.offers), alert


def run_price_check(db: Session, source: PriceSource) -> CheckResult:
    """Check every watched game once. Safe to call from any thread."""
    if not _run_lock.acquire(blocking=False):
        raise CheckAlreadyRunning("A price check is already running")
    try:
        return _run(db, source)
    finally:
        _run_lock.release()


def _run(db: Session, source: PriceSource) -> CheckResult:
    result = CheckResult()
    items = db.scalars(
        select(WatchlistItem)
        .join(WatchlistItem.game)
        .where(Game.source == source.name)
        .options(joinedload(WatchlistItem.game))
        .order_by(WatchlistItem.id)
    ).all()
    if not items:
        return result

    try:
        all_details = source.get_games([i.game.external_id for i in items])
    except PriceSourceError as exc:
        log.warning("Price check failed: %s", exc)
        result.errors.append(str(exc))
        return result

    checked_at = utcnow()
    for item in items:
        details = all_details.get(item.game.external_id)
        if details is None:
            result.errors.append(f"No price data for {item.game.title!r}")
            continue
        saved, alert = record_check(db, item, details, checked_at)
        result.checked += 1
        result.prices_saved += saved
        result.alerts_created += 1 if alert else 0
    db.commit()
    log.info("Price check done: %s", result)
    return result
