"""Database tables (SQLAlchemy ORM models)."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

MONEY = Numeric(10, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Game(Base):
    """A game as known by one price source (e.g. CheapShark game id 612)."""

    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_games_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255))
    thumb_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    watch: Mapped["WatchlistItem | None"] = relationship(
        back_populates="game", cascade="all, delete-orphan", uselist=False
    )
    prices: Mapped[list["PricePoint"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class WatchlistItem(Base):
    """'Alert me when this game is under $X.' One per game."""

    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True
    )
    target_price: Mapped[Decimal] = mapped_column(MONEY)
    # Lowest price we already alerted about. Prevents duplicate alerts.
    # Reset to NULL when the price goes back to/above the target.
    last_alerted_price: Mapped[Decimal | None] = mapped_column(MONEY)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    game: Mapped[Game] = relationship(back_populates="watch")
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class PricePoint(Base):
    """One store's price for one game at one moment (price history)."""

    __tablename__ = "price_points"
    __table_args__ = (Index("ix_price_points_game_checked", "game_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    store_id: Mapped[str] = mapped_column(String(50))
    store_name: Mapped[str] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(MONEY)
    regular_price: Mapped[Decimal | None] = mapped_column(MONEY)
    deal_url: Mapped[str | None] = mapped_column(String(500))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    game: Mapped[Game] = relationship(back_populates="prices")


class Alert(Base):
    """Created by the price checker when a watched game drops below target."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_item_id: Mapped[int] = mapped_column(
        ForeignKey("watchlist_items.id", ondelete="CASCADE"), index=True
    )
    price: Mapped[Decimal] = mapped_column(MONEY)
    target_price: Mapped[Decimal] = mapped_column(MONEY)
    store_name: Mapped[str] = mapped_column(String(100))
    deal_url: Mapped[str | None] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[WatchlistItem] = relationship(back_populates="alerts")
