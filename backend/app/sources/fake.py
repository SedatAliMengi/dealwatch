"""A fake price source with fixed, made-up prices.

Used by the tests and for an offline demo (PRICE_SOURCE=fake). No network.
Tests can change a price with `set_price` to simulate a sale.
"""

from __future__ import annotations

import copy
import threading
from decimal import Decimal

from app.sources.base import GameDetails, GameSummary, Offer, PriceSource, register

# external_id -> title + {store_id: (store_name, price, regular_price)}
DEFAULT_CATALOG: dict[str, dict] = {
    "1": {
        "title": "Starfall Courier",
        "offers": {"1": ("Steam", "24.99", "39.99"), "7": ("GOG", "27.49", "39.99")},
    },
    "2": {
        "title": "Hollow Lantern",
        "offers": {"1": ("Steam", "14.99", "14.99"), "25": ("Epic Games Store", "9.99", "14.99")},
    },
    "3": {
        "title": "Pixel Pirates",
        "offers": {"1": ("Steam", "4.99", "19.99")},
    },
    "4": {
        "title": "Neon Drift",
        "offers": {"7": ("GOG", "29.99", "29.99"), "25": ("Epic Games Store", "29.99", "29.99")},
    },
    "5": {
        "title": "Ironwood Tactics",
        "offers": {"1": ("Steam", "17.99", "44.99"), "7": ("GOG", "19.79", "44.99")},
    },
    "6": {"title": "Moonlit Farm", "offers": {}},  # a game with no current deals
}


@register
class FakeSource(PriceSource):
    name = "fake"

    def __init__(self, catalog: dict[str, dict] | None = None):
        self._catalog = copy.deepcopy(catalog if catalog is not None else DEFAULT_CATALOG)
        self._lock = threading.Lock()

    def set_price(self, external_id: str, store_id: str, price: str | Decimal,
                  store_name: str = "Steam") -> None:
        with self._lock:
            offers = self._catalog[external_id]["offers"]
            name, _, regular = offers.get(store_id, (store_name, None, None))
            offers[store_id] = (name, str(price), regular)

    def remove_offer(self, external_id: str, store_id: str) -> None:
        with self._lock:
            self._catalog[external_id]["offers"].pop(store_id, None)

    def search(self, query: str, limit: int = 10) -> list[GameSummary]:
        q = query.lower().strip()
        results = []
        for external_id, game in self._catalog.items():
            if q in game["title"].lower():
                details = self.get_game(external_id)
                best = details.best_offer if details else None
                results.append(
                    GameSummary(
                        external_id=external_id,
                        title=game["title"],
                        cheapest_price=best.price if best else None,
                    )
                )
        return results[:limit]

    def get_game(self, external_id: str) -> GameDetails | None:
        with self._lock:
            game = self._catalog.get(external_id)
            if game is None:
                return None
            offers = tuple(
                sorted(
                    (
                        Offer(
                            store_id=store_id,
                            store_name=name,
                            price=Decimal(price),
                            regular_price=Decimal(regular) if regular else None,
                        )
                        for store_id, (name, price, regular) in game["offers"].items()
                    ),
                    key=lambda o: o.price,
                )
            )
            return GameDetails(external_id=external_id, title=game["title"], offers=offers)
