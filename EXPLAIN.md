# Dealwatch, explained simply

This file explains how the project works in plain words, so you can talk about it with confidence.
Every technical word is explained in one sentence the first time it appears (in **bold**).

---

## 1. The big picture

Dealwatch has three parts:

1. A **frontend**, the part of an app that runs in your browser and that people see and click. Ours is written in **React**, a JavaScript library for building web pages out of small reusable pieces called **components**.
2. A **backend**, the part that runs on a server, holds the rules and talks to the database. Ours is written in Python with **FastAPI**, a framework (a ready-made toolkit) for building web APIs.
3. A **database**, a program that stores data safely in tables so it is still there after a restart. We use **PostgreSQL** (often called "Postgres"), a popular free database.

The frontend and backend talk through an **API** (Application Programming Interface), a list of web addresses the backend answers, each doing one job, like `GET /api/watchlist`.
They send data as **JSON**, a simple text format for data, like `{"title": "Hollow Knight", "price": 14.99}`.

Prices come from **CheapShark**, a free website that collects game prices from many stores and offers its own API.

---

## 2. How a request travels: React → API → service → database

Example: you type a target of $10 for "Hollow Knight" and click **Watch**.

1. **React (browser).** The `Search` component calls `api.addWatch("165363", "10")` in `frontend/src/api.js`. That sends an **HTTP request**, a message from the browser to a server, of type **POST** (the HTTP verb meaning "create something") to `/api/watchlist` with the JSON body `{"external_id": "165363", "target_price": "10"}`.

2. **nginx (only in Docker).** **nginx** is a small, fast web server. It gives the browser the React files and forwards every `/api/...` request to the FastAPI container. That way the page and the API share one address, so the browser has no cross-site rules to complain about.

3. **Router (FastAPI).** A **router** is the code that says "this address + this verb runs this function". `app/routers/watchlist.py` has `add_to_watchlist()`.
   Before the function runs, FastAPI uses **Pydantic**, a library that checks data against a declared shape, to check the body with the `WatchlistCreate` **schema** (the description of what valid data looks like). If `target_price` is `-5` or `"cheap"`, FastAPI stops here and answers **422**, the HTTP status code for "your data is invalid".

4. **Dependencies.** The router function asks for a database **session** (one open conversation with the database) and for the current **PriceSource** (explained in section 4). FastAPI's **dependency injection**, a way to hand a function the things it needs instead of the function creating them, gives it both. This is why tests can swap in a fake source easily.

5. **Service.** The router calls `watchlist.add_item()` in `app/services/watchlist.py`. A **service** is a plain Python function holding the business rules, with no web code in it.
   It checks: is this game already watched? If yes it raises `ConflictError`, which becomes **409** ("conflict").
   It asks the PriceSource for the game. If the game does not exist it raises `NotFoundError`, which becomes **404** ("not found").

6. **Database through the ORM.** The service creates Python objects `Game` and `WatchlistItem`. **SQLAlchemy** is an **ORM** (Object-Relational Mapper), a library that turns Python objects into database rows and back, so we rarely write SQL (the database's own language) by hand.
   It also saves today's prices as the first **price history** rows, and calls `db.commit()`. A **commit** makes all the changes permanent together; if something fails before it, nothing is saved (this "all or nothing" unit is called a **transaction**).

7. **Back to the browser.** The router turns the saved item into the `WatchlistOut` schema, FastAPI turns that into JSON, and returns status **201** ("created"). React then reloads the watchlist and shows the new row and its chart.

Short version: **click → fetch → nginx → router (validate) → service (rules) → SQLAlchemy → Postgres → back as JSON → React redraws.**

---

## 3. How the price checker works, step by step

The **price checker** is the code that looks up prices on its own, without anybody clicking anything. It lives in `app/services/price_checker.py`.

**Who starts it?**
- **APScheduler**, a Python library that runs a function on a timer, calls it every `CHECK_INTERVAL_HOURS` (6 by default). It is set up in `app/scheduler.py` and started when the API starts.
- You can also start it by hand with `POST /api/checker/run` (the "Check prices now" button).

**What it does:**

1. **Lock.** It takes a **lock**, a flag only one piece of code can hold at a time. If a check is already running (for example the timer and the button at the same moment), the second one stops with "already running". This prevents double prices and double alerts.
2. **Load the watchlist.** It reads every watched game from the database in one query.
3. **Fetch prices in bulk.** It calls `source.get_games([...all ids...])` once. CheapShark can answer 25 games per request, so 50 games need only 2 requests.
4. **If the source fails** (no internet, rate limit), it writes the error in the result and stops calmly. Nothing crashes, and the next run will try again.
5. **For each game:**
   - Save every store's price as a `PricePoint` row with the same timestamp. This is the **price history**.
   - Find the best (lowest) price.
   - Call `decide_alert()`, the rule that decides if you get an alert:
     - price **at or above** target → no alert, and the game is "re-armed" (we forget the last alert price);
     - price **below** target and **never alerted** → create an alert;
     - price **below** target and **lower than the last alert** → create a new alert (it dropped even more);
     - price **below** target but **same or higher than the last alert** → no alert (we already told you).
6. **Commit** everything at once.
7. **Return a summary**: how many games were checked, prices saved, alerts created, and errors.

**Why "no duplicate alerts" matters:** a game on sale for two weeks would otherwise create an alert every 6 hours, 56 alerts for one sale. With the rule above you get exactly one, and another only if the price goes even lower or the sale ends and starts again.

---

## 4. The PriceSource plug-in design

**The problem:** today prices come from CheapShark. Tomorrow you may want eBay, or a store's own API. If CheapShark code were spread across the app, every change would touch many files and could break things.

**The idea:** a **plug-in design**, where the main program defines a "socket" and different pieces can be plugged into it without changing the program.
Our socket is `PriceSource` in `app/sources/base.py`. It is an **interface** (in Python an **abstract base class**), a class that only lists the methods every real source must have:

- `search(query)` → list of games
- `get_game(id)` → that game's prices in every store, or `None`
- `get_games(ids)` → many games at once (has a default that just calls `get_game` in a loop)

Everything else in the app (services, checker, API) only talks to this interface. It never knows whether it is talking to CheapShark or something else.

**The plugs we have:**
- `CheapSharkSource` (`cheapshark.py`): the real one, over the internet, with caching and throttling.
- `FakeSource` (`fake.py`): fixed, made-up prices kept in memory. Tests use it because it is fast, never fails randomly, and lets a test say "now the price is $15" with `set_price()`. It also powers the offline demo.

**How a new store is added (one file):**
1. Create `app/sources/ebay.py`.
2. Write `@register class EbaySource(PriceSource): name = "ebay"` and fill in `search` and `get_game`.
3. Set `PRICE_SOURCE=ebay`.

That works because `registry.py` automatically imports every file in `app/sources/`, and `@register` is a **decorator**, a line starting with `@` that wraps a class or function to add behaviour; here it adds the class to a dictionary of sources by name.

**Why it is useful:**
- **Easy to extend**: one new file, no edits elsewhere.
- **Easy to test**: tests swap in `FakeSource`, no internet needed.
- **Safer**: a bug or API change at CheapShark is fixed in one file.
- **Same data everywhere**: every source returns the same small data classes (`GameSummary`, `Offer`, `GameDetails`), so the rest of the code does not care where data came from.

**Being polite to CheapShark** (all inside `cheapshark.py`):
- **Cache**: a short-term memory of answers. If we asked the same question less than 10 minutes ago, we reuse the answer instead of calling CheapShark again.
- **Throttle**: we wait at least 1 second between real requests.
- **Rate limit handling**: a **rate limit** is a rule like "max N requests per minute". If CheapShark answers **429** ("too many requests"), we stop and report it instead of hammering them.
- **Redirect links**: deal links use CheapShark's redirect URL, as they ask, and the page credits CheapShark.

---

## 5. Why each tool was chosen

| Tool | What it is (one sentence) | Why here |
|---|---|---|
| **Python 3.12** | A popular, readable programming language. | Asked for the job; great web and data libraries. |
| **FastAPI** | A modern Python framework for building APIs. | Fast to write, checks input automatically, and creates the `/docs` page for free. |
| **Pydantic** | A library that checks data has the right shape and types. | Gives clear 422 errors and documents the API shapes. |
| **PostgreSQL** | A reliable, free, widely used relational database. | Industry standard; exact money type (`NUMERIC`); good constraints. |
| **SQLAlchemy** | The standard Python ORM. | Write Python instead of raw SQL; same code works on Postgres and SQLite. |
| **Alembic** | A tool for **migrations**, step-by-step scripts that change the database structure over time. | The schema is versioned in git, and a fresh database gets it with one command. |
| **APScheduler** | A library that runs functions on a schedule. | Runs the checker inside the API, no extra server needed. |
| **httpx** | A Python library for making HTTP requests. | Clean API, timeouts, and a mock transport that lets tests fake CheapShark. |
| **pytest** + **pytest-cov** | The most used Python test tool, plus a plug-in that measures **coverage** (the share of code lines the tests run). | Simple tests; the build fails if coverage drops under 80%. |
| **Docker** | A tool that packs an app and everything it needs into a **container**, a small isolated box that runs the same on every computer. | "Works on my machine" problems disappear. |
| **docker compose** | A tool that starts several containers together from one file. | `docker compose up` starts Postgres, the API and the web page at once. |
| **GitHub Actions** | GitHub's built-in **CI** (Continuous Integration: running checks automatically on every code push). | Every push runs all tests on real Postgres, builds the page and starts the whole stack. |
| **React + Vite** | React builds the page from components; **Vite** is a fast tool that runs and bundles the frontend code. | Small, common, quick to start. |
| **nginx** | A fast web server and **reverse proxy** (a server that forwards requests to another server). | Serves the built page and forwards `/api` to FastAPI. |

---

## 6. Words you will hear in interviews

- **Endpoint**: one address + verb in the API, like `DELETE /api/watchlist/3`.
- **Status code**: the number the server answers with: 200 OK, 201 created, 204 done with no body, 404 not found, 409 conflict, 422 invalid input, 502 the server behind us failed.
- **Foreign key**: a column pointing to a row in another table, like `watchlist_items.game_id → games.id`.
- **Cascade delete**: when a parent row is deleted, its child rows are deleted automatically (remove a watch → its alerts go too).
- **Unique constraint**: a database rule that forbids two rows with the same value (one watch per game).
- **Index**: a database lookup structure that makes searching a column fast, like the index at the back of a book.
- **Mock**: a fake replacement for something real in a test, like a fake CheapShark that answers instantly.
- **Idempotent**: doing something twice gives the same result as once (running the checker twice does not create two alerts).

---

## 7. 20 likely interview questions (short answers to say out loud)

**1. What does Dealwatch do?**
"It watches game prices across stores using the CheapShark API. You set a target price, a background job checks prices every few hours, saves price history, and creates an alert when the price drops below your target."

**2. Walk me through a request.**
"React sends a POST to `/api/watchlist`. FastAPI validates the body with Pydantic, the router calls the watchlist service, the service checks the rules and asks the price source for the game, saves it with SQLAlchemy, and commits. The router returns JSON with status 201."

**3. Why split code into routers, services, models, schemas?**
"Each layer has one job. Routers handle HTTP, services hold business rules, models describe tables, schemas describe the API shapes. So I can test the rules without HTTP, and change the API without touching the rules."

**4. What is the PriceSource interface and why?**
"It is an abstract class with `search` and `get_game`. The whole app only talks to it. CheapShark is one implementation, a fake one is another. Adding eBay is one new file. It also makes tests fast and reliable because they use the fake source."

**5. How do you add a new store?**
"Create one file in `app/sources`, subclass `PriceSource`, give it a name, add `@register`. The registry imports all files in that folder automatically, so then you just set `PRICE_SOURCE` to the new name."

**6. How do you avoid duplicate alerts?**
"Each watch stores the last price we alerted at. We only alert again if the new price is lower than that. When the price goes back above the target, we clear it, so the next drop alerts again. It is one small function, `decide_alert`, with tests for each case."

**7. What if two price checks run at the same time?**
"APScheduler is set to `max_instances=1`, and the checker takes a lock. If the button is pressed during a scheduled run, the API answers 409 'already running'."

**8. How do you respect CheapShark's limits?**
"I cache responses for 10 minutes, wait at least one second between requests, fetch up to 25 games in one call, stop on HTTP 429, and link deals through their redirect URL with credit on the page."

**9. What happens if CheapShark is down?**
"For user requests, the source raises `PriceSourceError` and the API returns 502 with a clear message. In the background checker the error is recorded in the result and the job just tries again next time. Nothing crashes."

**10. Why store money as Decimal and not float?**
"Floats can't store most decimals exactly, so 0.1 plus 0.2 isn't exactly 0.3. With Decimal in Python and NUMERIC(10,2) in Postgres, cents are always exact."

**11. How did you test it?**
"80 pytest tests, 99% coverage. API tests through FastAPI's TestClient, database tests for constraints and cascades, checker tests for below/above/equal/no-duplicate cases, and CheapShark tests with a mocked HTTP layer for parsing, caching, throttling and errors. All use the fake source, so no network."

**12. Do the tests use a real database?**
"Locally they use SQLite in memory for speed. In GitHub Actions the same tests run on a real PostgreSQL 16 service. The database address comes from an environment variable, so the test code is the same."

**13. Why Alembic migrations, not just `create_all`?**
"Migrations are versioned changes to the schema, stored in git. On a real database with data you can't drop and recreate tables. I also have a test that runs the migration and compares the result with the models, so they can't drift apart."

**14. How do you handle validation errors?**
"Pydantic schemas: target price must be over 0, at most 10,000, max 2 decimals. Invalid input gets a 422 automatically. My own errors are `NotFoundError` and `ConflictError`, which one central handler turns into 404 and 409 with a `detail` message."

**15. Why run the scheduler inside the API instead of a separate worker?**
"For this size it keeps deployment simple: one container. The trade-off is that with several API copies, each would run the job. Then I'd move the checker to its own worker or use a database lock. The checker function itself wouldn't change."

**16. How is the price history stored and shown?**
"Every check saves one row per store with a timestamp. The history endpoint groups by check time and returns the best price per check, oldest first. React draws it as a small SVG line chart with the target as a dashed line."

**17. How do you keep secrets out of the repo?**
"Settings come from environment variables. The repo only has `.env.example` with placeholder values; `.env` is in `.gitignore`. Docker compose reads `.env` if it exists."

**18. What does Docker compose start?**
"Three containers: Postgres with a health check, the API which runs migrations then starts uvicorn, and nginx serving the React build and forwarding `/api` to the API. One command: `docker compose up --build`."

**19. What does your CI do?**
"On every push GitHub Actions runs migrations up and down on Postgres, runs all tests with an 80% coverage minimum, builds the React app, then starts the full docker compose stack and checks the API and page answer."

**20. What would you improve next?**
"User accounts so each person has their own watchlist, sending alerts by email or Discord, a separate worker for the checker, Redis for a shared cache, and showing more than one source at once."

---

## 8. Two-minute pitch

"Dealwatch is a game price alert app. The backend is FastAPI with PostgreSQL, SQLAlchemy and Alembic. You search games through the CheapShark API, put them on a watchlist with a target price, and a scheduled job checks prices every few hours, saves history, and creates alerts when a price drops below the target, without duplicates. All price fetching sits behind one `PriceSource` interface, so CheapShark is just one plug-in and a fake source is used for tests; adding a store is one file. It has 80 tests at 99% coverage, runs with one `docker compose up`, and GitHub Actions tests it on real Postgres on every push. There's a small React page to search, manage the watchlist, see alerts and a price chart."
