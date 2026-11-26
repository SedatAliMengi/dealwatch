"""Watchlist endpoints: create, read, update, delete, history, errors."""


def add(client, external_id="1", target=20):
    return client.post("/api/watchlist", json={"external_id": external_id, "target_price": target})


def test_add_game_returns_201_with_latest_price(client):
    r = add(client, "1", 20)
    assert r.status_code == 201
    body = r.json()
    assert body["game"]["title"] == "Starfall Courier"
    assert body["game"]["source"] == "fake"
    assert body["target_price"] == 20.0
    assert body["latest_price"] == 24.99
    assert body["latest_store"] == "Steam"
    assert body["below_target"] is False


def test_add_below_target_is_flagged(client):
    body = add(client, "3", 10).json()
    assert body["below_target"] is True


def test_list_watchlist(client):
    add(client, "1")
    add(client, "2")
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    assert {i["game"]["title"] for i in r.json()} == {"Starfall Courier", "Hollow Lantern"}


def test_list_empty_watchlist(client):
    assert client.get("/api/watchlist").json() == []


def test_get_one_item(client):
    item_id = add(client).json()["id"]
    r = client.get(f"/api/watchlist/{item_id}")
    assert r.status_code == 200
    assert r.json()["id"] == item_id


def test_adding_same_game_twice_is_409(client):
    add(client, "1")
    r = add(client, "1")
    assert r.status_code == 409
    assert "already on your watchlist" in r.json()["detail"]


def test_adding_unknown_game_is_404(client):
    r = add(client, "999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_update_target_price(client):
    item_id = add(client).json()["id"]
    r = client.patch(f"/api/watchlist/{item_id}", json={"target_price": "30.50"})
    assert r.status_code == 200
    assert r.json()["target_price"] == 30.5
    assert r.json()["below_target"] is True


def test_delete_item_then_404(client):
    item_id = add(client).json()["id"]
    assert client.delete(f"/api/watchlist/{item_id}").status_code == 204
    assert client.get(f"/api/watchlist/{item_id}").status_code == 404
    assert client.delete(f"/api/watchlist/{item_id}").status_code == 404


def test_readd_after_delete_works(client):
    item_id = add(client).json()["id"]
    client.delete(f"/api/watchlist/{item_id}")
    assert add(client).status_code == 201


def test_unknown_item_is_404_everywhere(client):
    assert client.get("/api/watchlist/12345").status_code == 404
    assert client.patch("/api/watchlist/12345", json={"target_price": 5}).status_code == 404
    assert client.get("/api/watchlist/12345/history").status_code == 404


def test_validation_errors_are_422(client):
    cases = [
        {"external_id": "1"},  # missing target
        {"external_id": "1", "target_price": 0},
        {"external_id": "1", "target_price": -5},
        {"external_id": "1", "target_price": "1.999"},  # too many decimals
        {"external_id": "1", "target_price": 20000},
        {"external_id": "1", "target_price": "cheap"},
        {"external_id": "", "target_price": 10},
    ]
    for body in cases:
        r = client.post("/api/watchlist", json=body)
        assert r.status_code == 422, body
        assert "detail" in r.json()
    assert client.get("/api/watchlist/not-a-number").status_code == 422


def test_price_history_is_best_price_per_check(client, fake_source):
    item_id = add(client, "1", 20).json()["id"]
    fake_source.set_price("1", "1", "18.00")
    client.post("/api/checker/run")
    r = client.get(f"/api/watchlist/{item_id}/history")
    assert r.status_code == 200
    prices = [p["price"] for p in r.json()]
    assert prices == [24.99, 18.0]
    assert r.json()[0]["store_name"] == "Steam"


def test_history_limit_keeps_newest(client, fake_source):
    item_id = add(client, "1", 20).json()["id"]
    fake_source.set_price("1", "1", "18.00")
    client.post("/api/checker/run")
    r = client.get(f"/api/watchlist/{item_id}/history?limit=1")
    assert [p["price"] for p in r.json()] == [18.0]
