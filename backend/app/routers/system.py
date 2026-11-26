from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_db, get_source
from app.schemas import CheckResultOut, ErrorOut, HealthOut
from app.services.price_checker import run_price_check
from app.sources import PriceSource

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(db: Annotated[Session, Depends(get_db)], source: Annotated[PriceSource, Depends(get_source)]):
    """Is the API up, and can it reach the database?"""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - health check reports, never crashes
        database = "unavailable"
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        database=database,
        price_source=source.name,
    )


@router.post(
    "/checker/run", response_model=CheckResultOut, responses={409: {"model": ErrorOut}}
)
def run_checker_now(
    db: Annotated[Session, Depends(get_db)],
    source: Annotated[PriceSource, Depends(get_source)],
):
    """Run the price checker right now instead of waiting for the schedule."""
    return CheckResultOut.model_validate(run_price_check(db, source))
