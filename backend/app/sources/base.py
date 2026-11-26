"""The PriceSource plug-in interface.

Every store/price provider (CheapShark, a fake one for tests, eBay later...)
is a subclass of PriceSource. The rest of the app only talks to this
interface, so it never knows or cares which provider is behind it.

To add a provider: create ONE new file in this folder, subclass
PriceSource, give it a unique `name`, and decorate it with @register.
It is then selectable with PRICE_SOURCE=<name>.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:  # pragma: no cover
    from app.config import Settings


class PriceSourceError(Exception):
    """The provider could not be reached or returned something unusable."""


@dataclass(frozen=True)
class GameSummary:
    """One search result."""

    external_id: str
    title: str
    thumb_url: str | None = None
    cheapest_price: Decimal | None = None


@dataclass(frozen=True)
class Offer:
    """One store's current price for a game."""

    store_id: str
    store_name: str
    price: Decimal
    regular_price: Decimal | None = None
    deal_url: str | None = None


@dataclass(frozen=True)
class GameDetails:
    """A game plus its current offers across stores."""

    external_id: str
    title: str
    thumb_url: str | None = None
    offers: tuple[Offer, ...] = field(default_factory=tuple)

    @property
    def best_offer(self) -> Offer | None:
        return min(self.offers, key=lambda o: o.price, default=None)


class PriceSource(ABC):
    """Interface every price provider implements."""

    name: ClassVar[str]

    @classmethod
    def from_settings(cls, settings: Settings) -> PriceSource:
        """Build the source from app settings. Override if you need config."""
        return cls()

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[GameSummary]:
        """Find games whose title matches `query`."""

    @abstractmethod
    def get_game(self, external_id: str) -> GameDetails | None:
        """Current offers for one game, or None if the id is unknown."""

    def get_games(self, external_ids: Sequence[str]) -> dict[str, GameDetails]:
        """Offers for many games. Default: one call per game.

        Sources with a bulk endpoint should override this to save requests.
        Unknown ids are simply missing from the result.
        """
        result: dict[str, GameDetails] = {}
        for external_id in external_ids:
            details = self.get_game(external_id)
            if details is not None:
                result[external_id] = details
        return result


_REGISTRY: dict[str, type[PriceSource]] = {}


def register(cls: type[PriceSource]) -> type[PriceSource]:
    """Class decorator that makes a source selectable by its `name`."""
    if not getattr(cls, "name", None):
        raise TypeError(f"{cls.__name__} must define a non-empty `name`")
    _REGISTRY[cls.name] = cls
    return cls
