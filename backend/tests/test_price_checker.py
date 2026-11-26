"""Price checker logic: alerts below target, none above, no duplicates."""

import threading
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Alert, PricePoint
from app.services import watchlist
from app.services.price_checker import (
    CheckAlreadyRunning,
    _run_lock,
    run_price_check,
)
from app.sources import PriceSource, PriceSourceError


def alert_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Alert))


def watch(db, source, external_id="1", target="20.00"):
    return watchlist.add_item(db, source, external_id, Decimal(target))


def test_price_below_target_creates_alert(db, fake_source):
    item = watch(db, fake_source, "1", "30.00")  # best price is 24.99 at Steam
    alerts = db.scalars(select(Alert)).all()
    assert len(alerts) == 1
    assert alerts[0].price == Decimal("24.99")
    assert alerts[0].target_price == Decimal("30.00")
    assert alerts[0].store_name == "Steam"
    assert alerts[0].watchlist_item_id == item.id
    assert not alerts[0].is_read


def test_price_above_target_creates_no_alert(db, fake_source):
    watch(db, fake_source, "1", "20.00")
    result = run_price_check(db, fake_source)
    assert result.checked == 1
    assert result.alerts_created == 0
    assert alert_count(db) == 0


def test_price_equal_to_target_creates_no_alert(db, fake_source):
    watch(db, fake_source, "1", "24.99")
    assert alert_count(db) == 0


def test_price_drop_on_later_check_creates_alert(db, fake_source):
    watch(db, fake_source, "1", "20.00")
    fake_source.set_price("1", "1", "19.49")
    result = run_price_check(db, fake_source)
    assert result.alerts_created == 1
    assert db.scalar(select(Alert)).price == Decimal("19.49")


def test_no_duplicate_alerts_for_same_price(db, fake_source):
    watch(db, fake_source, "1", "30.00")
    for _ in range(3):
        assert run_price_check(db, fake_source).alerts_created == 0
    assert alert_count(db) == 1


def test_further_drop_creates_new_alert(db, fake_source):
    watch(db, fake_source, "1", "30.00")
    fake_source.set_price("1", "1", "19.99")
    assert run_price_check(db, fake_source).alerts_created == 1
    fake_source.set_price("1", "1", "21.99")  # went up, still below target
    assert run_price_check(db, fake_source).alerts_created == 0
    assert alert_count(db) == 2


def test_price_recovers_then_drops_again_alerts_again(db, fake_source):
    watch(db, fake_source, "1", "30.00")  # alert #1 at 24.99
    fake_source.set_price("1", "1", "39.99")
    fake_source.set_price("1", "7", "39.99")
    assert run_price_check(db, fake_source).alerts_created == 0  # back above: re-arm
    fake_source.set_price("1", "1", "24.99")
    assert run_price_check(db, fake_source).alerts_created == 1
    assert alert_count(db) == 2


def test_changing_target_allows_a_fresh_alert(db, fake_source):
    item = watch(db, fake_source, "1", "30.00")
    watchlist.update_target(db, item.id, Decimal("26.00"))
    assert run_price_check(db, fake_source).alerts_created == 1


def test_checker_saves_every_offer_as_history(db, fake_source):
    watch(db, fake_source, "1", "10.00")  # 2 offers saved on add
    result = run_price_check(db, fake_source)
    assert result.prices_saved == 2
    assert db.scalar(select(func.count()).select_from(PricePoint)) == 4


def test_game_without_offers_is_checked_without_alert(db, fake_source):
    watch(db, fake_source, "6", "10.00")
    result = run_price_check(db, fake_source)
    assert result.checked == 1 and result.prices_saved == 0 and result.alerts_created == 0


def test_empty_watchlist_does_nothing(db, fake_source):
    assert run_price_check(db, fake_source).checked == 0


def test_game_missing_from_source_is_reported(db, fake_source):
    watch(db, fake_source, "1")
    del fake_source._catalog["1"]
    result = run_price_check(db, fake_source)
    assert result.checked == 0
    assert "Starfall Courier" in result.errors[0]


class BrokenSource(PriceSource):
    name = "fake"  # pretend to be the same source the games came from

    def search(self, query, limit=10):
        raise PriceSourceError("down")

    def get_game(self, external_id):
        raise PriceSourceError("down")


def test_source_failure_is_recorded_not_raised(db, fake_source):
    watch(db, fake_source, "1")
    result = run_price_check(db, BrokenSource())
    assert result.errors == ["down"]
    assert result.checked == 0


def test_only_one_check_runs_at_a_time(db, fake_source):
    assert _run_lock.acquire()
    try:
        with pytest.raises(CheckAlreadyRunning):
            run_price_check(db, fake_source)
    finally:
        _run_lock.release()


def test_lock_is_released_after_a_run(db, fake_source):
    run_price_check(db, fake_source)
    assert not _run_lock.locked()
    t = threading.Thread(target=run_price_check, args=(db, fake_source))
    t.start()
    t.join()
