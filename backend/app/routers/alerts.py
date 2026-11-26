from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import Alert
from app.schemas import AlertOut, ErrorOut, MarkAllReadOut
from app.services import alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])
DB = Annotated[Session, Depends(get_db)]


def _to_out(alert: Alert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        watchlist_item_id=alert.watchlist_item_id,
        game_title=alert.item.game.title,
        price=alert.price,
        target_price=alert.target_price,
        store_name=alert.store_name,
        deal_url=alert.deal_url,
        is_read=alert.is_read,
        created_at=alert.created_at,
    )


@router.get("", response_model=list[AlertOut])
def list_alerts(
    db: DB,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Newest first. Use ?unread_only=true for just the new ones."""
    return [_to_out(a) for a in alerts.list_alerts(db, unread_only, limit)]


@router.post("/{alert_id}/read", response_model=AlertOut, responses={404: {"model": ErrorOut}})
def mark_alert_read(alert_id: int, db: DB):
    return _to_out(alerts.mark_read(db, alert_id))


@router.post("/read-all", response_model=MarkAllReadOut)
def mark_all_alerts_read(db: DB):
    return MarkAllReadOut(updated=alerts.mark_all_read(db))
