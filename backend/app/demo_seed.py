"""Fill the database with demo data (FakeSource only, works offline).

    PRICE_SOURCE=fake python -m app.demo_seed

Adds three watched games and a few weeks of made-up price history so the
chart has something to show, then runs the price checker once.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.models import PricePoint, utcnow
from app.services import watchlist
from app.services.errors import ConflictError
from app.services.price_checker import run_price_check
from app.sources.fake import FakeSource

DEMO = [
    # external_id, target, weekly best prices (oldest first)
    ("1", "25.00", ["39.99", "39.99", "34.99", "29.99", "27.49", "24.99"]),
    ("2", "10.00", ["14.99", "14.99", "12.99", "14.99", "11.99", "9.99"]),
    ("5", "15.00", ["44.99", "29.99", "29.99", "22.49", "19.79", "17.99"]),
]


def seed(db: Session, source: FakeSource) -> None:
    now = utcnow()
    for external_id, target, history in DEMO:
        try:
            item = watchlist.add_item(db, source, external_id, Decimal(target))
        except ConflictError:
            continue
        weeks = len(history)
        for i, price in enumerate(history[:-1]):
            db.add(
                PricePoint(
                    game_id=item.game_id,
                    store_id="1",
                    store_name="Steam",
                    price=Decimal(price),
                    checked_at=now - timedelta(weeks=weeks - 1 - i),
                )
            )
        db.commit()
    run_price_check(db, source)


def main() -> None:  # pragma: no cover - thin CLI wrapper
    settings = get_settings()
    if settings.price_source != "fake":
        raise SystemExit("demo_seed only runs with PRICE_SOURCE=fake")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)  # no-op on a migrated database
    with make_session_factory(engine)() as db:
        seed(db, FakeSource())
    print("Demo data added.")


if __name__ == "__main__":  # pragma: no cover
    main()
