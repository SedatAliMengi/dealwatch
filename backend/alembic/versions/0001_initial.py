"""Initial tables: games, watchlist_items, price_points, alerts.

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

MONEY = sa.Numeric(10, 2)


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("thumb_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_games_source_external_id"),
    )
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("target_price", MONEY, nullable=False),
        sa.Column("last_alerted_price", MONEY, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "price_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("store_name", sa.String(100), nullable=False),
        sa.Column("price", MONEY, nullable=False),
        sa.Column("regular_price", MONEY, nullable=True),
        sa.Column("deal_url", sa.String(500), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_points_game_checked", "price_points", ["game_id", "checked_at"])
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "watchlist_item_id",
            sa.Integer(),
            sa.ForeignKey("watchlist_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", MONEY, nullable=False),
        sa.Column("target_price", MONEY, nullable=False),
        sa.Column("store_name", sa.String(100), nullable=False),
        sa.Column("deal_url", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alerts_watchlist_item_id", "alerts", ["watchlist_item_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_watchlist_item_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_price_points_game_checked", table_name="price_points")
    op.drop_table("price_points")
    op.drop_table("watchlist_items")
    op.drop_table("games")
