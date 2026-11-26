"""PriceSource plug-ins: CheapShark (with a mocked network), Fake, registry."""

from decimal import Decimal

import httpx
import pytest

from app.cache import MISSING, TTLCache
from app.config import Settings
from app.sources import GameDetails, PriceSource, PriceSourceError, register
from app.sources.base import _REGISTRY
from app.sources.cheapshark import CheapSharkSource
from app.sources.fake import FakeSource
from app.sources.registry import available_sources, create_source

STORES = [
    {"storeID": "1", "storeName": "Steam"},
    {"storeID": "7", "storeName": "GOG"},
]
GAME_612 = {
    "info": {"title": "LEGO Batman", "steamAppID": "21000", "thumb": "https://img/612.jpg"},
    "cheapestPriceEver": {"price": "3.99", "date": 1543028665},
    "deals": [
        {"storeID": "1", "dealID": "abc", "price": "19.99", "retailPrice": "19.99"},
        {"storeID": "7", "dealID": "def", "price": "4.99", "retailPrice": "19.99"},
        {"storeID": "99", "dealID": "ghi", "price": "not-a-price", "retailPrice": ""},
    ],
}
SEARCH = [
    {"gameID": "612", "cheapest": "4.99", "external": "LEGO Batman", "thumb": "https://img/612.jpg"},
    {"gameID": "613", "cheapest": "", "internalName": "LEGOBATMAN2", "thumb": ""},
]


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 3))
        self.now += seconds


def make_source(handler, clock=None, **kwargs):
    clock = clock or FakeClock()
    return CheapSharkSource(
        transport=httpx.MockTransport(handler), clock=clock, sleep=clock.sleep, **kwargs
    )


def router(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    if request.url.path.endswith("/stores"):
        return httpx.Response(200, json=STORES)
    if "title" in params:
        return httpx.Response(200, json=SEARCH)
    if params.get("id") == "612":
        return httpx.Response(200, json=GAME_612)
    if "ids" in params:
        ids = params["ids"].split(",")
        return httpx.Response(200, json={i: GAME_612 for i in ids if i != "404"})
    return httpx.Response(200, json=[])  # how CheapShark answers unknown ids


# ---- CheapShark --------------------------------------------------------


def test_cheapshark_search_parses_results():
    results = make_source(router).search("batman")
    assert results[0].external_id == "612"
    assert results[0].title == "LEGO Batman"
    assert results[0].cheapest_price == Decimal("4.99")
    assert results[1].title == "LEGOBATMAN2"
    assert results[1].cheapest_price is None and results[1].thumb_url is None


def test_cheapshark_get_game_parses_offers_and_links():
    game = make_source(router).get_game("612")
    assert game.title == "LEGO Batman"
    assert [o.store_name for o in game.offers] == ["GOG", "Steam"]  # cheapest first, bad row skipped
    assert game.best_offer.price == Decimal("4.99")
    assert game.best_offer.regular_price == Decimal("19.99")
    # CheapShark asks that deals link through their redirect.
    assert game.best_offer.deal_url == "https://www.cheapshark.com/redirect?dealID=def"


def test_cheapshark_unknown_game_is_none():
    assert make_source(router).get_game("nope") is None


def test_cheapshark_unknown_store_gets_placeholder_name():
    def handler(request):
        if request.url.path.endswith("/stores"):
            return httpx.Response(200, json={"weird": True})
        return httpx.Response(200, json=GAME_612)

    names = {o.store_name for o in make_source(handler).get_game("612").offers}
    assert names == {"Store 1", "Store 7"}


def test_cheapshark_bulk_uses_one_request_per_25_games():
    source = make_source(router)
    ids = [str(i) for i in range(30)] + ["404", "1"]  # "1" is a duplicate
    games = source.get_games(ids)
    assert len(games) == 30 and "404" not in games
    assert source.request_count == 3  # 2 chunks + 1 stores lookup


def test_cheapshark_caches_responses():
    source = make_source(router)
    source.search("batman")
    source.search("batman")
    assert source.request_count == 1


def test_cheapshark_cache_expires():
    clock = FakeClock()
    source = make_source(router, clock=clock, cache_seconds=60)
    source.search("batman")
    clock.now += 61
    source.search("batman")
    assert source.request_count == 2


def test_cheapshark_waits_between_requests():
    clock = FakeClock()
    source = make_source(router, clock=clock, min_interval_seconds=1.0)
    source.search("a1")
    clock.now += 0.25
    source.search("a2")
    assert clock.slept == [0.75]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(429), "rate limit"),
        (httpx.Response(500), "HTTP 500"),
        (httpx.Response(200, content=b"<html>"), "invalid JSON"),
        (httpx.Response(200, json={"not": "a list"}), "Unexpected search"),
    ],
)
def test_cheapshark_bad_responses_raise_source_error(response, message):
    source = make_source(lambda request: response)
    with pytest.raises(PriceSourceError, match=message):
        source.search("batman")


def test_cheapshark_bad_bulk_response_raises():
    source = make_source(lambda request: httpx.Response(200, json=[]))
    with pytest.raises(PriceSourceError, match="Unexpected bulk"):
        source.get_games(["1"])


def test_cheapshark_network_error_raises_source_error():
    def handler(request):
        raise httpx.ConnectError("no internet")

    with pytest.raises(PriceSourceError, match="Could not reach"):
        make_source(handler).search("batman")


def test_cheapshark_from_settings():
    s = Settings(cheapshark_cache_seconds=5, cheapshark_min_interval_seconds=2)
    source = CheapSharkSource.from_settings(s)
    assert source._cache.ttl_seconds == 5 and source._min_interval == 2


# ---- Fake + base -------------------------------------------------------


def test_fake_source_search_and_get():
    fake = FakeSource()
    assert [g.title for g in fake.search("pixel")] == ["Pixel Pirates"]
    assert fake.get_game("2").best_offer.store_name == "Epic Games Store"
    assert fake.get_game("6").best_offer is None
    assert fake.get_game("missing") is None


def test_fake_source_set_and_remove_price():
    fake = FakeSource()
    fake.set_price("3", "99", "1.00", store_name="Humble")
    assert fake.get_game("3").best_offer.store_name == "Humble"
    fake.remove_offer("3", "99")
    assert fake.get_game("3").best_offer.store_name == "Steam"


def test_default_get_games_loops_over_get_game():
    games = FakeSource().get_games(["1", "missing", "2"])
    assert set(games) == {"1", "2"}
    assert isinstance(games["1"], GameDetails)


# ---- registry: the plug-in mechanism ------------------------------------


def test_registry_lists_builtin_sources():
    assert {"cheapshark", "fake"} <= set(available_sources())


def test_registry_builds_sources_by_name():
    assert isinstance(create_source("fake", Settings()), FakeSource)
    assert isinstance(create_source("cheapshark", Settings()), CheapSharkSource)


def test_registry_unknown_name_is_clear_error():
    with pytest.raises(ValueError, match="Unknown price source 'ebay'"):
        create_source("ebay", Settings())


def test_new_source_only_needs_a_class_with_register():
    @register
    class EbaySource(PriceSource):
        name = "ebay-test"

        def search(self, query, limit=10):
            return []

        def get_game(self, external_id):
            return None

    try:
        assert isinstance(create_source("ebay-test", Settings()), EbaySource)
    finally:
        _REGISTRY.pop("ebay-test")


def test_register_requires_a_name():
    with pytest.raises(TypeError):

        @register
        class Nameless(PriceSource):  # noqa: F841
            def search(self, query, limit=10):
                return []

            def get_game(self, external_id):
                return None


# ---- cache -------------------------------------------------------------


def test_ttl_cache_basics():
    clock = FakeClock()
    cache = TTLCache(10, clock=clock)
    assert cache.get("k") is MISSING
    cache.set("k", 1)
    assert cache.get("k") == 1
    cache.set("zero", 1, ttl_seconds=0)  # ttl 0 = don't cache
    assert cache.get("zero") is MISSING
    clock.now += 10
    assert cache.get("k") is MISSING
    cache.set("k", 2)
    cache.clear()
    assert cache.get("k") is MISSING
