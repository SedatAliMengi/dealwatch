"""Runs the price checker in the background every N hours (APScheduler)."""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.services.price_checker import CheckAlreadyRunning, run_price_check
from app.sources import PriceSource

log = logging.getLogger(__name__)
JOB_ID = "price-check"


def scheduled_check(session_factory: sessionmaker, source: PriceSource) -> None:
    """The job itself. Never raises: a failed run must not kill the scheduler."""
    with session_factory() as db:
        try:
            run_price_check(db, source)
        except CheckAlreadyRunning:
            log.info("Skipping scheduled check: one is already running")
        except Exception:
            log.exception("Scheduled price check crashed")


def build_scheduler(
    settings: Settings, session_factory: sessionmaker, source: PriceSource
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    extra = {"next_run_time": datetime.now(timezone.utc)} if settings.run_check_on_startup else {}
    scheduler.add_job(
        scheduled_check,
        "interval",
        hours=settings.check_interval_hours,
        args=[session_factory, source],
        id=JOB_ID,
        max_instances=1,  # never two checks at once
        coalesce=True,  # if runs were missed (e.g. laptop asleep), run once
        **extra,
    )
    return scheduler
