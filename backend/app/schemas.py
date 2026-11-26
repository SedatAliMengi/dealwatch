"""Pydantic schemas: the shape of API requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Money is a Decimal inside the app (no float rounding errors) but is sent
# as a plain JSON number so the frontend can use it directly.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
TargetPrice = Annotated[
    Decimal,
    Field(gt=0, le=10000, max_digits=7, decimal_places=2, examples=["19.99"]),
]


class GameSearchResult(BaseModel):
    external_id: str
    title: str
    thumb_url: str | None
    cheapest_price: Money | None


class OfferOut(BaseModel):
    store_id: str
    store_name: str
    price: Money
    regular_price: Money | None
    deal_url: str | None


class GameOffersOut(BaseModel):
    external_id: str
    title: str
    thumb_url: str | None
    offers: list[OfferOut]


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    title: str
    thumb_url: str | None


class WatchlistCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=100, examples=["612"])
    target_price: TargetPrice


class WatchlistUpdate(BaseModel):
    target_price: TargetPrice


class WatchlistOut(BaseModel):
    id: int
    game: GameOut
    target_price: Money
    latest_price: Money | None = None
    latest_store: str | None = None
    latest_deal_url: str | None = None
    latest_checked_at: datetime | None = None
    below_target: bool = False
    created_at: datetime
    updated_at: datetime


class PriceHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    checked_at: datetime
    price: Money
    store_name: str


class AlertOut(BaseModel):
    id: int
    watchlist_item_id: int
    game_title: str
    price: Money
    target_price: Money
    store_name: str
    deal_url: str | None
    is_read: bool
    created_at: datetime


class MarkAllReadOut(BaseModel):
    updated: int


class CheckResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    checked: int
    prices_saved: int
    alerts_created: int
    errors: list[str]


class HealthOut(BaseModel):
    status: str
    database: str
    price_source: str


class ErrorOut(BaseModel):
    detail: str
