# Dealwatch

**Watch game prices across Steam, Epic, GOG and more, and get an alert when a game drops below your target price.**

FastAPI + PostgreSQL + SQLAlchemy/Alembic backend with a background price checker, a pluggable `PriceSource` design, 80 tests (99% coverage), Docker and CI, plus a small React page.

![Dealwatch screenshot](docs/screenshot.png)

*(Screenshot uses the offline demo data from `FakeSource`, so the game titles are made up.)*

---

## Features

- **Search** games by name and see the cheapest current price ([CheapShark API](https://www.cheapshark.com/api)).
- **Watchlist**: add a game with a target price ("alert me under $20"), list, change the target, remove.
- **Price checker**: runs inside the API every few hours (configurable). It fetches prices for every watched game, saves them as **price history**, and creates an **alert** when the best price drops below the target. No duplicate alerts.
- **Alerts**: list, filter unread, mark one or all as read.
- **Price history chart** per game on the web page.

## Run it (one command)

Needs [Docker](https://docs.docker.com/get-docker/).

```bash
git clone https://github.com/SedatAliMengi/dealwatch.git
cd dealwatch
docker compose up --build
```

| What | URL |
|---|---|
| Web page | http://localhost:8080 |
| API docs (Swagger) | http://localhost:8000/docs |

This starts three containers: PostgreSQL, the API (runs database migrations on start) and the React page served by nginx.
Settings come from `.env` if you create one (`cp .env.example .env`); otherwise safe local defaults are used.

**Offline demo** (no internet needed, fills in sample data):

```bash
PRICE_SOURCE=fake DEMO_SEED=true docker compose up --build
```

### Windows desktop app (double-click, no Docker)

Needs Python 3.11+ and Node.js (Node is only needed to build the page once, or after you change it).

1. Double-click **`Create Desktop Shortcut.bat`** once. A **Dealwatch** icon appears on your desktop.
2. Double-click the icon (or `Start Dealwatch.vbs`). **No console window opens.** The first start sets everything up, then http://localhost:8765 opens in your browser.
3. Dealwatch keeps running in the **tray** (the icons next to the clock). Right-click its icon for **Open Dealwatch**, **Check prices now**, **Show log** and **Quit Dealwatch**.

Double-clicking again while it runs just opens the page; it never starts a second copy.

How it works: [`launcher/start.ps1`](launcher/start.ps1) runs hidden, shows the tray icon, and starts the API with SQLite. FastAPI also serves the built React page, so it's one process. Your data is in `data/dealwatch.db`, and logs are in `data/launcher.log` (setup) and `data/server.log` (the API). Every start also runs one price check.

**Moving the folder:** move or rename it whenever you like (stop Dealwatch first from the tray), even to a path with spaces or commas. The desktop icon keeps working. It doesn't point into the project folder; it runs a small helper in `%LOCALAPPDATA%\Dealwatch` that remembers where the project is. If the project has moved, the helper searches Desktop, Documents and Downloads for it, then remembers the new place. If you put it somewhere else, double-click `Start Dealwatch.vbs` in the new folder once. Your data moves with the folder.

**Updating:** pull or edit the code and start it as usual. The launcher notices changed `requirements.txt` or frontend files and reinstalls or rebuilds only what changed. New database migrations are applied automatically.

Optional settings go in `backend\.env` (see `.env.example`), e.g. `PRICE_SOURCE=fake`. To change the port, set the `DEALWATCH_PORT` environment variable.

### Run without Docker (developer mode)

```bash
# API (Python 3.11+). SQLite by default, so no database to install.
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:create_app --factory --reload

# Web page (Node 20+), in a second terminal
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

## Tests

```bash
cd backend
pytest                             # SQLite in memory, ~4 seconds
```

- **80 tests, 99% coverage**. `pytest` fails if coverage drops under 80%.
- To run the same tests on PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/dealwatch_test pytest`
- **GitHub Actions** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push:
  1. migrations up/down + all tests on a real **PostgreSQL 16**,
  2. the React production build,
  3. `docker compose up` of the full stack and HTTP smoke checks through nginx.

| Test file | What it covers |
|---|---|
| `test_price_checker.py` | below target → alert, above/equal → no alert, no duplicates, further drop → new alert, recover then drop → new alert, source failure, one-run-at-a-time lock |
| `test_api_watchlist.py` | CRUD, 404, 409, 422 validation, price history |
| `test_api_games_alerts_system.py` | search, offers, 502 when the source is down, alerts, checker trigger, health |
| `test_sources.py` | CheapShark parsing / caching / throttling / errors (HTTP mocked), FakeSource, the plug-in registry |
| `test_database.py` | unique + cascade rules, exact money math, migrations match models, scheduler, demo seed |

## API

All endpoints are under `/api`. Interactive docs: http://localhost:8000/docs

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | API + database status |
| GET | `/api/games/search?q=batman&limit=10` | Search games, cheapest price each |
| GET | `/api/games/{external_id}/offers` | Current price in every store |
| GET | `/api/watchlist` | Watched games with latest best price |
| POST | `/api/watchlist` | Watch a game `{"external_id": "612", "target_price": 19.99}` |
| GET | `/api/watchlist/{id}` | One watched game |
| PATCH | `/api/watchlist/{id}` | Change target `{"target_price": 15}` |
| DELETE | `/api/watchlist/{id}` | Stop watching (204) |
| GET | `/api/watchlist/{id}/history` | Best price at each check (for the chart) |
| GET | `/api/alerts?unread_only=true` | Alerts, newest first |
| POST | `/api/alerts/{id}/read` | Mark one alert read |
| POST | `/api/alerts/read-all` | Mark all read |
| POST | `/api/checker/run` | Run the price checker now |

### Examples

```bash
curl "http://localhost:8000/api/games/search?q=hollow%20knight&limit=2"
```
```json
[
  {"external_id": "165363", "title": "Hollow Knight", "thumb_url": "https://...", "cheapest_price": 14.99},
  {"external_id": "307927", "title": "Hollow Knight: Silksong", "thumb_url": "https://...", "cheapest_price": 19.99}
]
```

```bash
curl -X POST http://localhost:8000/api/watchlist \
  -H "Content-Type: application/json" \
  -d '{"external_id": "165363", "target_price": 10}'
```
```json
{
  "id": 1,
  "game": {"id": 1, "source": "cheapshark", "external_id": "165363", "title": "Hollow Knight", "thumb_url": "https://..."},
  "target_price": 10.0,
  "latest_price": 14.99,
  "latest_store": "GOG",
  "latest_deal_url": "https://www.cheapshark.com/redirect?dealID=...",
  "latest_checked_at": "2026-11-26T14:01:12Z",
  "below_target": false,
  "created_at": "2026-11-26T14:01:12Z",
  "updated_at": "2026-11-26T14:01:12Z"
}
```

```bash
curl -X POST http://localhost:8000/api/checker/run
```
```json
{"checked": 1, "prices_saved": 3, "alerts_created": 0, "errors": []}
```

**Errors** always look like `{"detail": "..."}`:

| Code | When |
|---|---|
| 404 | Unknown watchlist item, alert, or game id |
| 409 | Game already on the watchlist, or a price check is already running |
| 422 | Invalid input, e.g. `target_price` ≤ 0, more than 2 decimals, or a missing field |
| 502 | The price source (CheapShark) is down or rate-limiting us |

## Project structure

```
backend/
  app/
    main.py            builds the FastAPI app, error handlers, starts the scheduler
    config.py          settings from environment variables
    db.py, models.py   SQLAlchemy engine + tables
    schemas.py         Pydantic request/response shapes
    routers/           HTTP endpoints only (thin)
    services/          business logic: watchlist, alerts, price_checker, catalog
    sources/           PriceSource plug-ins: base.py, cheapshark.py, fake.py, registry.py
    scheduler.py       APScheduler job for the price checker
  alembic/             database migrations
  tests/
frontend/              React (Vite) page, nginx config for Docker
launcher/              Windows double-click launcher + desktop shortcut + icon
docker-compose.yml     db + api + web
```

## Design decisions

### 1. The `PriceSource` plug-in

All price fetching goes through one small interface ([`app/sources/base.py`](backend/app/sources/base.py)):

```python
class PriceSource(ABC):
    name: ClassVar[str]
    def search(self, query: str, limit: int = 10) -> list[GameSummary]: ...
    def get_game(self, external_id: str) -> GameDetails | None: ...
    def get_games(self, external_ids) -> dict[str, GameDetails]:  # default: loop get_game
```

- The services, the checker and the API only know this interface. They never import CheapShark.
- **`CheapSharkSource`** is the real one. **`FakeSource`** has fixed prices; tests use it (fast, no network) and it powers the offline demo.
- Sources register themselves with `@register`, and [`registry.py`](backend/app/sources/registry.py) imports every module in `app/sources/` automatically. **Adding eBay = one new file** `app/sources/ebay.py` with `@register class EbaySource(PriceSource): name = "ebay"`, then `PRICE_SOURCE=ebay`. Nothing else changes. A test proves this (`test_new_source_only_needs_a_class_with_register`).
- Sources return plain dataclasses (`GameSummary`, `Offer`, `GameDetails`), not raw JSON, so the rest of the app is the same for every provider.
- Each game row stores which `source` it came from, so ids from different providers never collide.

### 2. Being polite to CheapShark

CheapShark is free and asks API users to be reasonable. `CheapSharkSource`:
- **caches** every response in memory (10 min by default; the store list for 24 h),
- **throttles**: at least 1 second between real HTTP requests,
- **batches**: the checker asks for up to 25 games in one request (`/games?ids=...`), so 50 watched games = 2 requests, not 50,
- **stops on HTTP 429** (rate limited) and reports the error instead of retrying in a loop,
- **links deals through CheapShark's redirect URL** (`https://www.cheapshark.com/redirect?dealID=...`) and credits CheapShark on the page.

### 3. No duplicate alerts

Each watchlist item remembers `last_alerted_price`.
- Best price ≥ target → no alert, and `last_alerted_price` is cleared ("re-armed").
- Best price < target → alert only if we never alerted, or the price is **lower** than the last alert.
- Changing the target also re-arms the item.

So a game sitting at $9.99 for a week makes **one** alert, not 28. If it drops further to $7.99 you hear about it again.
The rule lives in one small pure function, `decide_alert()`, which makes it easy to test.

### 4. Other choices

- **Money is `Decimal` / `NUMERIC(10,2)`**, never float, so $0.10 + $0.20 is exactly $0.30. It is sent as a JSON number for the frontend.
- **Routers are thin; services hold the logic.** Services raise `NotFoundError` / `ConflictError`; `main.py` maps them to 404 / 409 in one place.
- **App factory** (`create_app(settings, session_factory, source)`): tests build an app with their own DB and `FakeSource`, no global state to patch.
- **Scheduler inside the API process** (APScheduler) keeps deployment to one container. `max_instances=1`, `coalesce=True` and a lock stop two checks running at once (scheduled + manual). For many API replicas you would move it to a separate worker; the checker function would not change.
- **Tests run on SQLite locally and on PostgreSQL in CI**, same code (`TEST_DATABASE_URL`). A test also checks that the Alembic migration produces exactly the schema the models describe.
- **Watching a game saves its prices right away**, so the chart and "below target" status are useful immediately, not after the first scheduled run.
- **No secrets in the repo**: only `.env.example`; `.env` is git-ignored.

## Configuration

See [`.env.example`](.env.example). The main ones:

| Variable | Default | Meaning |
|---|---|---|
| `PRICE_SOURCE` | `cheapshark` | Which plug-in: `cheapshark` or `fake` |
| `CHECK_INTERVAL_HOURS` | `6` | How often the checker runs |
| `RUN_CHECK_ON_STARTUP` | `false` | Also run once when the API starts |
| `SCHEDULER_ENABLED` | `true` | Turn the background checker off |
| `CHEAPSHARK_CACHE_SECONDS` | `600` | Response cache time |
| `CHEAPSHARK_MIN_INTERVAL_SECONDS` | `1` | Minimum gap between requests |
| `DEMO_SEED` | `false` | Add sample data on start (fake source only) |

## Credits

Price data is provided by **[CheapShark](https://www.cheapshark.com)**. Dealwatch is not affiliated with CheapShark. Deal links go through CheapShark's redirect, as their API asks.

## License

[PolyForm Noncommercial 1.0.0](LICENSE). Free for noncommercial use.

Required Notice: Copyright (c) 2026 Sedat Ali Mengi
