"""Search, offers, alerts, checker trigger and health endpoints."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.sources import PriceSource, PriceSourceError


# ---- games -------------------------------------------------------------


def test_search_finds_games_case_insensitive(client):
    r = client.get("/api/games/search", params={"q": "HOLLOW"})
    assert r.status_code == 200
    assert r.json() == [
        {"external_id": "2", "title": "Hollow Lantern", "thumb_url": None, "cheapest_price": 9.99}
    ]


def test_search_respects_limit(client):
    r = client.get("/api/games/search", params={"q": "on", "limit": 2})
    assert len(r.json()) == 2


def test_search_needs_a_query(client):
    assert client.get("/api/games/search").status_code == 422
    assert client.get("/api/games/search", params={"q": "a"}).status_code == 422
    assert client.get("/api/games/search", params={"q": "ab", "limit": 0}).status_code == 422


def test_offers_cheapest_first(client):
    r = client.get("/api/games/2/offers")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Hollow Lantern"
    assert [o["store_name"] for o in body["offers"]] == ["Epic Games Store", "Steam"]
    assert body["offers"][0]["regular_price"] == 14.99


def test_offers_unknown_game_is_404(client):
    assert client.get("/api/games/nope/offers").status_code == 404


class DownSource(PriceSource):
    name = "down"

    def search(self, query, limit=10):
        raise PriceSourceError("CheapShark rate limit reached")

    def get_game(self, external_id):
        raise PriceSourceError("timeout")


def test_source_errors_become_502(settings, session_factory):
    app = create_app(settings=settings, session_factory=session_factory, source=DownSource())
    with TestClient(app) as c:
        r = c.get("/api/games/search", params={"q": "zelda"})
        assert r.status_code == 502
        assert "rate limit" in r.json()["detail"]
        assert c.post("/api/watchlist", json={"external_id": "1", "target_price": 5}).status_code == 502


# ---- alerts ------------------------------------------------------------


def make_alerts(client):
    client.post("/api/watchlist", json={"external_id": "3", "target_price": 10})  # 4.99
    client.post("/api/watchlist", json={"external_id": "2", "target_price": 12})  # 9.99


def test_list_alerts_newest_first(client):
    make_alerts(client)
    r = client.get("/api/alerts")
    assert r.status_code == 200
    titles = [a["game_title"] for a in r.json()]
    assert titles == ["Hollow Lantern", "Pixel Pirates"]
    assert r.json()[0]["price"] == 9.99
    assert r.json()[0]["is_read"] is False


def test_mark_alert_read_and_filter_unread(client):
    make_alerts(client)
    first = client.get("/api/alerts").json()[0]["id"]
    r = client.post(f"/api/alerts/{first}/read")
    assert r.status_code == 200 and r.json()["is_read"] is True
    unread = client.get("/api/alerts", params={"unread_only": True}).json()
    assert [a["game_title"] for a in unread] == ["Pixel Pirates"]


def test_mark_all_read(client):
    make_alerts(client)
    assert client.post("/api/alerts/read-all").json() == {"updated": 2}
    assert client.get("/api/alerts?unread_only=true").json() == []


def test_mark_unknown_alert_is_404(client):
    assert client.post("/api/alerts/999/read").status_code == 404


def test_deleting_watch_removes_its_alerts(client):
    make_alerts(client)
    item_id = client.get("/api/watchlist").json()[0]["id"]
    client.delete(f"/api/watchlist/{item_id}")
    assert len(client.get("/api/alerts").json()) == 1


# ---- system ------------------------------------------------------------


def test_health(client):
    assert client.get("/api/health").json() == {
        "status": "ok",
        "database": "ok",
        "price_source": "fake",
    }


def test_health_reports_broken_database(client):
    class BrokenSession:
        def execute(self, *_):
            raise RuntimeError("db down")

        def close(self):
            pass

    client.app.state.session_factory = BrokenSession
    body = client.get("/api/health").json()
    assert body["status"] == "degraded" and body["database"] == "unavailable"


def test_run_checker_endpoint(client, fake_source):
    client.post("/api/watchlist", json={"external_id": "1", "target_price": 20})
    fake_source.set_price("1", "1", "15.00")
    r = client.post("/api/checker/run")
    assert r.status_code == 200
    assert r.json() == {"checked": 1, "prices_saved": 2, "alerts_created": 1, "errors": []}


def test_run_checker_while_running_is_409(client):
    from app.services.price_checker import _run_lock

    _run_lock.acquire()
    try:
        r = client.post("/api/checker/run")
        assert r.status_code == 409
    finally:
        _run_lock.release()


def test_openapi_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert "/api/watchlist" in client.get("/openapi.json").json()["paths"]
