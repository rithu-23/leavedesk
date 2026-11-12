# LeaveDesk

LeaveDesk is an employee leave-management app, built step by step during the AYPOLS Enablement Workshop.

- **Day 1:** a specification (`SPEC.md`) and a plain-Python domain package with the leave rules.
- **Day 2 (current):** a tested REST API with FastAPI (`API_SPEC.md`), running in Docker.
- **Day 3:** storage on PostgreSQL.
- **Day 4:** an Angular front end.

## Requirements

- Python 3.12 or newer, Git
- Docker Desktop (for `docker compose`)

## Quick start with Docker

```bash
git clone https://github.com/rithu-23/leavedesk.git
cd leavedesk
cp .env.example .env          # then replace every value in .env
docker compose up --build
```

Open http://localhost:8000/docs, click **Authorize** and sign in as `ana@leavedesk.test`,
`mo@leavedesk.test` (manager) or `lee@leavedesk.test` (manager) with the `DEMO_PASSWORD` from `.env`.

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
| `leavedesk/demo.py` | Day 1 demo of the happy path and every edge case |
| `tests/` | Domain tests; `tests/api/` holds the API tests |
| `SPEC.md`, `API_SPEC.md` | Specifications and acceptance criteria |
| `AI_NOTES.md` | Log of AI assistance and what was checked or fixed |
| `Dockerfile`, `docker-compose.yml` | Container image and the `api` + `db` services |
| `.env.example` | Every setting the app needs, with placeholder values |
| `requirements.txt`, `requirements-dev.txt` | Runtime libraries; test and lint tools |
| `pyproject.toml` | pytest and Ruff settings |
