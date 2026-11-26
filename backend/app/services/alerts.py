"""Alerts: list them and mark them as read."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models import Alert, WatchlistItem
from app.services.errors import NotFoundError


def list_alerts(db: Session, unread_only: bool = False, limit: int = 100) -> list[Alert]:
    query = (
        select(Alert)
        .options(joinedload(Alert.item).joinedload(WatchlistItem.game))
        .order_by(Alert.created_at.desc(), Alert.id.desc())
        .limit(limit)
    )
    if unread_only:
        query = query.where(Alert.is_read.is_(False))
    return list(db.scalars(query))


def mark_read(db: Session, alert_id: int) -> Alert:
    alert = db.get(
        Alert, alert_id, options=[joinedload(Alert.item).joinedload(WatchlistItem.game)]
    )
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    alert.is_read = True
    db.commit()
    return alert


def mark_all_read(db: Session) -> int:
    result = db.execute(update(Alert).where(Alert.is_read.is_(False)).values(is_read=True))
    db.commit()
    return result.rowcount
