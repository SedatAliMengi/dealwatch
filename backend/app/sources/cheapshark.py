"""CheapShark price source (https://www.cheapshark.com/api).

CheapShark is free and needs no API key. In return they ask clients to be
polite. This source therefore:
  * caches every response in memory (default 10 minutes, stores list 24h),
  * waits at least `min_interval_seconds` between real HTTP requests,
  * fetches many games in ONE request (`/games?ids=...`, up to 25 ids),
  * stops on HTTP 429 (rate limited) instead of retrying in a loop,
  * links deals through CheapShark's redirect URL, as their docs request.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.cache import MISSING, TTLCache
from app.config import Settings
from app.sources.base import (
    GameDetails,
    GameSummary,
    Offer,
    PriceSource,
    PriceSourceError,
    register,
)

DEAL_REDIRECT_URL = "https://www.cheapshark.com/redirect?dealID={deal_id}"
STORES_TTL_SECONDS = 24 * 60 * 60
BULK_LIMIT = 25  # CheapShark accepts up to 25 ids per /games?ids= call


def _money(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


@register
class CheapSharkSource(PriceSource):
    name = "cheapshark"

    def __init__(
        self,
        base_url: str = "https://www.cheapshark.com/api/1.0",
        cache_seconds: float = 600,
        min_interval_seconds: float = 1.0,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "Dealwatch/1.0 (open-source price alert demo)"},
        )
        self._cache = TTLCache(cache_seconds, clock=clock)
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._request_lock = threading.Lock()
        self._last_request_at: float | None = None
        self.request_count = 0  # handy for tests and debugging

    @classmethod
    def from_settings(cls, settings: Settings) -> CheapSharkSource:
        return cls(
            base_url=settings.cheapshark_base_url,
            cache_seconds=settings.cheapshark_cache_seconds,
            min_interval_seconds=settings.cheapshark_min_interval_seconds,
            timeout_seconds=settings.http_timeout_seconds,
        )

    # ---- HTTP with cache + throttle -------------------------------------

    def _get(self, path: str, params: dict[str, Any], ttl: float | None = None) -> Any:
        key = (path, tuple(sorted(params.items())))
        cached = self._cache.get(key)
        if cached is not MISSING:
            return cached

        with self._request_lock:
            # Another thread may have fetched it while we waited for the lock.
            cached = self._cache.get(key)
            if cached is not MISSING:
                return cached

            if self._last_request_at is not None:
                wait = self._min_interval - (self._clock() - self._last_request_at)
                if wait > 0:
                    self._sleep(wait)
            try:
                self.request_count += 1
                response = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise PriceSourceError(f"Could not reach CheapShark: {exc}") from exc
            finally:
                self._last_request_at = self._clock()

        if response.status_code == 429:
            raise PriceSourceError("CheapShark rate limit reached, try again later")
        if response.status_code >= 400:
            raise PriceSourceError(f"CheapShark returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise PriceSourceError("CheapShark returned invalid JSON") from exc

        self._cache.set(key, data, ttl)
        return data

    def _store_names(self) -> dict[str, str]:
        data = self._get("/stores", {}, ttl=STORES_TTL_SECONDS)
        if not isinstance(data, list):
            return {}
        return {str(s.get("storeID")): s.get("storeName", "Unknown store") for s in data}

    # ---- PriceSource interface ------------------------------------------

    def search(self, query: str, limit: int = 10) -> list[GameSummary]:
        data = self._get("/games", {"title": query, "limit": limit})
        if not isinstance(data, list):
            raise PriceSourceError("Unexpected search response from CheapShark")
        return [
            GameSummary(
                external_id=str(g["gameID"]),
                title=g.get("external") or g.get("internalName") or "Unknown",
                thumb_url=g.get("thumb") or None,
                cheapest_price=_money(g.get("cheapest")),
            )
            for g in data
            if g.get("gameID")
        ]

    def get_game(self, external_id: str) -> GameDetails | None:
        data = self._get("/games", {"id": external_id})
        return self._parse_game(external_id, data)

    def get_games(self, external_ids: Sequence[str]) -> dict[str, GameDetails]:
        ids = list(dict.fromkeys(external_ids))  # de-duplicate, keep order
        result: dict[str, GameDetails] = {}
        for start in range(0, len(ids), BULK_LIMIT):
            chunk = ids[start : start + BULK_LIMIT]
            data = self._get("/games", {"ids": ",".join(chunk)})
            if not isinstance(data, dict):
                raise PriceSourceError("Unexpected bulk response from CheapShark")
            for external_id in chunk:
                details = self._parse_game(external_id, data.get(external_id))
                if details is not None:
                    result[external_id] = details
        return result

    def _parse_game(self, external_id: str, data: Any) -> GameDetails | None:
        # CheapShark answers an unknown id with an empty list.
        if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
            return None
        info = data["info"]
        stores = self._store_names() if data.get("deals") else {}
        offers = []
        for deal in data.get("deals") or []:
            price = _money(deal.get("price"))
            if price is None:
                continue
            store_id = str(deal.get("storeID", ""))
            deal_id = deal.get("dealID")
            offers.append(
                Offer(
                    store_id=store_id,
                    store_name=stores.get(store_id, f"Store {store_id}"),
                    price=price,
                    regular_price=_money(deal.get("retailPrice")),
                    deal_url=DEAL_REDIRECT_URL.format(deal_id=deal_id) if deal_id else None,
                )
            )
        return GameDetails(
            external_id=external_id,
            title=info.get("title") or "Unknown",
            thumb_url=info.get("thumb") or None,
            offers=tuple(sorted(offers, key=lambda o: o.price)),
        )
