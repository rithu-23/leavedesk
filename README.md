# LeaveDesk

LeaveDesk is an employee leave-management app, built step by step during the AYPOLS Enablement Workshop.

- **Day 1:** a specification (`SPEC.md`) and a plain-Python domain package with the leave rules.
- **Day 2:** a tested REST API with FastAPI (`API_SPEC.md`), running in Docker.
- **Day 3:** storage on PostgreSQL with SQLAlchemy 2 and Alembic (`SCHEMA.md`).
- **Day 4 (current):** an Angular web app (`UI_SPEC.md`), running in Docker behind nginx.

## Requirements

- Python 3.12 or newer, Git
- Docker Desktop (for `docker compose`)
- Node.js 22 or 24 and the Angular CLI (`npm install -g @angular/cli`), for working on the web app

## Quick start with Docker

```bash
git clone https://github.com/rithu-23/leavedesk.git
cd leavedesk
cp .env.example .env          # then replace every value in .env
docker compose up -d --build --wait
```

Open **http://localhost:8080** for the web app, or http://localhost:8000/docs for the API (click
**Authorize**). Sign in as `ana@leavedesk.test` (employee), `mo@leavedesk.test` (manager) or
`lee@leavedesk.test` (manager) with the `DEMO_PASSWORD` from `.env`.

## Local setup (macOS / Linux)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then replace every value in .env
```

| Task | Command |
|---|---|
| Run the API with auto-reload | `python -m uvicorn leavedesk.api.main:create_app --factory --reload` |
| Run the Day 1 demo | `python -m leavedesk.demo` |
| Run all tests | `python -m pytest` |
| Lint and format check | `ruff check . && ruff format --check .` |

## Database (Capstone 3)

PostgreSQL runs in Docker; Alembic and the tests connect to it from your Mac on `localhost:5433`
(not 5432, which a PostgreSQL installed directly on the Mac often already uses).
The first time (and whenever `docker/postgres-init/` changes), start from an empty volume so the
role script runs. This deletes all database data:

```bash
docker compose down -v
docker compose up -d db
```

| Task | Command |
|---|---|
| Apply migrations to the main database | `alembic upgrade head` |
| Check the models match the database | `alembic check` |
| Undo every migration | `alembic downgrade base` |
| Run only the database tests | `python -m pytest tests/db` |
| Run the **whole** suite on PostgreSQL (Day 2 tests included) | `scripts/pytest-postgres.sh` |
| Concurrency tests (two users at once) | `python -m pytest tests/db/test_concurrency.py -v` |
| Review demo: the same test **without** locks fails | `LEAVEDESK_DEMO_NO_LOCKS=1 python -m pytest tests/db/test_concurrency.py -k db10` |
| Run the outbox worker (sends anything left behind) | `python -m leavedesk.worker` (or `--once` for one pass) |
| Notification tests (outbox, rollback, LISTEN/NOTIFY) | `python -m pytest tests/db/test_outbox.py -v` |
| Seed 100k requests and capture query plans (PERF.md) | `python scripts/perf.py` → `perf_results.txt` |
| Log every SQL statement (N+1 checks) | `DB_ECHO=true python -m uvicorn leavedesk.api.main:create_app --factory` |
| Open a SQL prompt as the app role | `docker compose exec db psql -U leavedesk_app -d leavedesk` |

The two database roles (SCHEMA.md section 6): `leavedesk_migrator` owns the schema and runs Alembic;
`leavedesk_app` is what the API uses and cannot change the schema. Their passwords and URLs live in
`.env` (see `.env.example`). The tests in `tests/db` use the separate `leavedesk_test` database and
are skipped when `TEST_DATABASE_URL` / `TEST_MIGRATION_DATABASE_URL` are not set.

**Storage switch:** with `DATABASE_URL` set (as in `.env` and in Docker), the API uses PostgreSQL;
without it, the in-memory repository. `python -m pytest` runs the suite in memory;
`scripts/pytest-postgres.sh` runs the same tests, unchanged, against `leavedesk_test`. The repo-root
`conftest.py` migrates that database once and empties its tables before each test, and refuses to
run against any database whose name does not end in `_test`.

## Web app (Capstone 4)

The Angular app lives in `frontend/` (Angular 22: standalone components, signals, Angular
Material, Vitest, Playwright). The browser only ever calls `/api/...`: in development the Angular
dev server forwards it to `localhost:8000` (`frontend/proxy.conf.json`); in Docker, nginx forwards
it to the `api` service (`frontend/nginx.conf`). So the API needs no CORS settings.

Work on it with the API running on port 8000 (Docker, or `uvicorn` as above):

```bash
cd frontend
npm install
npm start                      # http://localhost:4200, reloads on every change
```

| Task (run in `frontend/`) | Command |
|---|---|
| Unit tests (Vitest + Angular Testing Library, HTTP mocked) | `npm test` |
| Lint (ESLint, including template accessibility rules) | `npm run lint` |
| Format check / fix (Prettier) | `npm run format:check` / `npm run format` |
| Production build | `npm run build` |
| End-to-end and accessibility tests (needs `docker compose up -d --build --wait`) | `npm run e2e` |
| First time only: Playwright's browser | `npx playwright install chromium` |
| Open the last Playwright report (screenshots and traces of failures) | `npx playwright show-report` |

Each successful end-to-end run uses one day of Ana's annual leave. To start again from the demo
data: `docker compose down -v && docker compose up -d --build --wait`.

## Project structure

| Path | What it holds |
|---|---|
| `leavedesk/domain/` | Business rules: models, exceptions, dates, balance, policies, repository, inbox, audit, notifications, `LeaveService` |
| `leavedesk/api/main.py` | FastAPI app factory |
| `leavedesk/api/routes/` | Auth, leave and notification endpoints |
| `leavedesk/api/security.py` | Argon2id password hashing and JWT tokens |
| `leavedesk/api/errors.py` | The single error format and exception handlers |
| `leavedesk/api/middleware.py` | Request ID and request logging |
| `leavedesk/api/stream.py` | Live notifications over Server-Sent Events |
| `leavedesk/db/` | SQLAlchemy models, engine, the PostgreSQL repository and login store |
| `migrations/`, `alembic.ini` | Alembic migrations (the only way the schema changes) |
| `docker/postgres-init/` | Creates the migrator and app roles and the test database on first start |
| `leavedesk/demo.py` | Day 1 demo of the happy path and every edge case |
| `tests/` | Domain tests; `tests/api/` holds the API tests; `tests/db/` needs PostgreSQL |
| `conftest.py`, `scripts/pytest-postgres.sh` | Run the whole suite on the PostgreSQL test database |
| `frontend/src/app/core/` | Angular: API types, error helper, auth service, JWT interceptor, route guards |
| `frontend/src/app/features/` | Angular features: `auth` (login), `leave` (store, My leave, Apply), `approvals` (lazy, managers only), `notifications` (bell, SSE store) |
| `frontend/src/app/shared/`, `frontend/src/app/layout/` | Reusable UI (confirm dialog, status chip, leave-type labels); the toolbar shell |
| `frontend/e2e/`, `frontend/playwright.config.ts` | Playwright end-to-end and accessibility tests |
| `frontend/Dockerfile`, `frontend/nginx.conf` | Web image: Node build, nginx serve and `/api` forwarding |
| `SPEC.md`, `API_SPEC.md`, `SCHEMA.md`, `PERF.md`, `UI_SPEC.md` | Specifications, acceptance criteria, the database design, the index proofs and the web app spec |
| `DEMO.md` | Script for the final demo |
| `AI_NOTES.md` | Log of AI assistance and what was checked or fixed |
| `Dockerfile`, `docker-compose.yml` | API image and the `db`, `migrate`, `api`, `worker` and `web` services |
| `.env.example` | Every setting the app needs, with placeholder values |
| `requirements.txt`, `requirements-dev.txt` | Runtime libraries; test and lint tools |
| `pyproject.toml` | pytest and Ruff settings |
