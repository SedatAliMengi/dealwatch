"""Database rules, migrations, scheduler and demo seed."""

from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError

from app import scheduler as scheduler_module
from app.config import Settings
from app.db import Base
from app.demo_seed import seed
from app.main import create_app
from app.models import Alert, Game, PricePoint, WatchlistItem
from app.services.price_checker import _run_lock

BACKEND_DIR = Path(__file__).resolve().parents[1]


# ---- constraints -------------------------------------------------------


def test_game_is_unique_per_source_and_external_id(db):
    db.add(Game(source="fake", external_id="1", title="A"))
    db.commit()
    db.add(Game(source="fake", external_id="1", title="B"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Game(source="cheapshark", external_id="1", title="C"))  # other source is fine
    db.commit()


def test_only_one_watchlist_item_per_game(db):
    game = Game(source="fake", external_id="1", title="A")
    db.add_all([game, WatchlistItem(game=game, target_price=Decimal("5"))])
    db.commit()
    db.add(WatchlistItem(game_id=game.id, target_price=Decimal("6")))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_money_keeps_exact_cents(db):
    game = Game(source="fake", external_id="9", title="A")
    db.add(PricePoint(game=game, store_id="1", store_name="Steam", price=Decimal("0.10")))
    db.commit()
    total = db.scalar(select(func.sum(PricePoint.price)))
    assert Decimal(total) + Decimal("0.20") == Decimal("0.30")


def test_deleting_game_cascades_to_everything(db):
    game = Game(source="fake", external_id="1", title="A")
    item = WatchlistItem(game=game, target_price=Decimal("5"))
    db.add_all([
        game,
        item,
        PricePoint(game=game, store_id="1", store_name="Steam", price=Decimal("4")),
        Alert(item=item, price=Decimal("4"), target_price=Decimal("5"), store_name="Steam"),
    ])
    db.commit()
    db.delete(game)
    db.commit()
    for model in (WatchlistItem, PricePoint, Alert):
        assert db.scalar(select(func.count()).select_from(model)) == 0


# ---- migrations --------------------------------------------------------


def test_migrations_create_schema_matching_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert {"games", "watchlist_items", "price_points", "alerts"} <= tables
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"Models and migrations differ: {diff}"

    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        assert "games" not in inspect(conn).get_table_names()
    engine.dispose()


# ---- scheduler ---------------------------------------------------------


def test_scheduler_job_is_configured(session_factory, fake_source):
    s = Settings(check_interval_hours=3, run_check_on_startup=True)
    sched = scheduler_module.build_scheduler(s, session_factory, fake_source)
    job = sched.get_job(scheduler_module.JOB_ID)
    assert job.trigger.interval.total_seconds() == 3 * 3600
    assert job.max_instances == 1 and job.coalesce is True
    assert job.next_run_time is not None  # runs right away on startup


def test_scheduled_check_runs_the_checker(session_factory, fake_source, db):
    from app.services import watchlist

    watchlist.add_item(db, fake_source, "1", Decimal("20"))
    fake_source.set_price("1", "1", "10.00")
    scheduler_module.scheduled_check(session_factory, fake_source)
    assert db.scalar(select(func.count()).select_from(Alert)) == 1


def test_scheduled_check_never_raises(session_factory, fake_source, monkeypatch):
    def boom(*_):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(scheduler_module, "run_price_check", boom)
    scheduler_module.scheduled_check(session_factory, fake_source)  # no exception

    _run_lock.acquire()
    monkeypatch.undo()
    try:
        scheduler_module.scheduled_check(session_factory, fake_source)  # skipped quietly
    finally:
        _run_lock.release()


def test_app_starts_and_stops_scheduler(session_factory, fake_source):
    s = Settings(price_source="fake", scheduler_enabled=True, check_interval_hours=24)
    app = create_app(settings=s, session_factory=session_factory, source=fake_source)
    with TestClient(app):
        assert app.state.scheduler.running
    assert not app.state.scheduler.running


def test_create_app_builds_its_own_engine_and_source(tmp_path):
    s = Settings(database_url=f"sqlite:///{tmp_path / 'x.db'}", price_source="fake",
                 scheduler_enabled=False)
    app = create_app(settings=s)
    assert app.state.price_source.name == "fake"


# ---- demo seed ---------------------------------------------------------


def test_demo_seed_creates_watchlist_history_and_alerts(db, fake_source):
    seed(db, fake_source)
    seed(db, fake_source)  # running twice is safe
    assert db.scalar(select(func.count()).select_from(WatchlistItem)) == 3
    assert db.scalar(select(func.count()).select_from(PricePoint)) > 15
    assert db.scalar(select(func.count()).select_from(Alert)) >= 2
