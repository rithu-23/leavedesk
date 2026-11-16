# AI Usage Notes

**Tool used:** Claude (claude.ai)
**How I use it:** I ask for step-by-step instructions and code, then read every line, run it, and check the result before committing. Anything I change, and why, is logged below.

---

## Entry 1 — Project setup (Day 1)

**Prompt:** Set up a Python 3.12+ project for LeaveDesk on macOS with a virtual environment, Pydantic v2, a .gitignore and a README.

**Generated:** Terminal commands (version checks, `git init`, venv creation, `pip install`), plus the `.gitignore` and `README.md` contents.

**Checked / changed:**
- Ran `python --version` and `which python` inside the venv to confirm it uses Python 3.12.16 from the project's `.venv` folder.
- Confirmed `requirements.txt` pins Pydantic **2.x** (2.14.3), not the old 1.x.
- Ran `git status` to confirm `.venv/` and cache files are ignored, so no installed libraries or secrets get committed.

**Issues caught:**
1. **Wrong assumption about Python:** the first instructions assumed `python3` would point to Python 3.12. On my Mac, `which -a python3` showed pyenv's shim runs first and points to 3.11.9. I created the venv with `python3.12` explicitly instead.
2. **Stale terminal:** `git status` failed with "Operation not permitted" because VS Code had reconnected an old terminal still sitting in the previous (trashed) project folder. Fixed by killing that terminal and opening a new one.
3. **Typo in my own .gitignore** (`".venv/` with a stray quote) meant `.venv` was still tracked (678 files showing). Caught by checking the Source Control count and `git status`; removed the quote.

---

## Entry 2 — SPEC.md (Day 1)

**Prompt:** Write SPEC.md for Capstone 1 in three parts: scope, entities and business rules; functional requirements with Given/When/Then acceptance criteria; error catalogue, edge cases and task breakdown.

**Generated:** Full SPEC.md draft: 8 business rules, 11 functional requirements with 32 acceptance criteria, an error catalogue, 16 edge cases and a 13-task breakdown.

**Checked / changed:**
- Read every business rule and decided to keep the suggested defaults (entitlements Annual 18 / Sick 12 / Casual 6; sick leave backdated up to 7 days; casual leave max 2 days per request).
- Checked the example dates with `cal 11 2026`: Mon 9 Nov is a Monday and 14–15 Nov is the weekend, so the day counts in the acceptance criteria are correct.
- Confirmed all five edge cases required by the capstone (end before start, weekends in range, overlap, insufficient balance, half day) appear as EC-1 to EC-5 and map to acceptance criteria.
- Confirmed insufficient balance maps to HTTP 422, matching the workshop's endpoint table.

**Issues caught:**
1. **Faulty shell command from AI:** `git show HEAD | grep '^-[^-]'` was meant to list deleted lines but silently returned nothing, because the deleted line began with a Markdown bullet (`--` in the diff). Replaced with `grep '^-' | grep -v '^---'`, which showed the real line. Lesson: a command that runs without an error can still give a wrong answer.
2. **File in the wrong folder:** SPEC.md was created inside the `leavedesk/` package instead of the project root (VS Code creates new files in the selected folder). Caught by `git add` failing; moved it with `mv`.
3. **Module name clash avoided:** The task breakdown names the date logic file `dates.py` rather than `calendar.py`, because `calendar` is already a Python standard-library module.


---

## Entry 3 — Exceptions, models and date logic (Day 1, tasks T2–T4)

**Prompt:** Implement exceptions.py, models.py (Pydantic v2) and dates.py from SPEC sections 3, 8, 9.2, BR-2 and BR-5.

**Generated:** A custom exception hierarchy with a LeaveDeskError base; Employee, LeaveRequest and Notification models with enums, Field limits and a model validator; pure functions for working-day counting and overlap detection.

**Checked / changed:**
- Ran every FR-2 acceptance criterion (AC-2.1 to AC-2.4) against the models: each raised ValidationError as specified. Also checked that changing `status` after creation is rejected (validate_assignment).
- Compared each Field limit with SPEC 9.2 (reason 10–500 after trimming, name 1–100, email pattern, enum values).
- Confirmed `id` and `created_at` use `default_factory` (a function), not `default` (a single value), so each request gets its own id.
- Ran the working-day counts from AC-1.1 to AC-1.4, EC-7 and AC-5.1 (3, 2, 0.5, 0, 0, 20) and five overlap shapes (same, partial, inside, touching, apart): all match the spec.
- Checked the `+ 1` in the day count (both ends included) and `<=` in the overlap formula (touching days overlap).

**Issues caught:**
1. **Error location for cross-field rules:** the end-date rule is a model-level validator, so Pydantic reports `loc = ()` instead of `('end_date',)`. The message still names end_date, which satisfies AC-2.1. Noted for the Capstone 2 error contract, where clients may need the field name.


---

## Entry 4 — Balance, policies, repository, instrumentation, service (Day 1, tasks T5–T9)

**Prompt:** Implement balance.py (dataclass), policies.py (abstract LeavePolicy and subclasses), repository.py (interface and in-memory implementation), instrumentation.py (@audit and timed) and service.py (LeaveService) from the spec.

**Generated:** LeaveBalance with reserve/confirm/release; LeavePolicy ABC using a template method with Annual, Sick and Casual subclasses; LeaveRepository ABC with a deep-copying in-memory implementation; @audit decorator supporting sync and async functions; LeaveService composed of repository, policies and an injected clock.

**Checked / changed:**
- Ran every BR-4 balance movement (AC-1.1, AC-5.1, AC-5.2, AC-6.1, AC-7.1, AC-8.1, AC-10.1) against LeaveBalance; a failed reserve leaves the balance unchanged.
- Ran every BR-3 policy criterion (AC-3.1 to AC-3.4, AC-1.4); confirmed exactly 7 days back is accepted (the boundary flagged in the PR #2 review) and that `LeavePolicy()` cannot be created.
- Confirmed the repository returns copies: a change is invisible until `save_request` is called.
- Confirmed @audit logs success and failure with duration, keeps the function name (functools.wraps) and re-raises errors (AC-11.2).
- Ran one end-to-end workflow covering FR-1 and FR-4 to FR-8, FR-10 and EC-16: every failure raised the error named in the spec, and balances were unchanged after each failure.
- Read service.py for check-then-change order, who-before-what authorisation, and a save after every change.

**Issues caught:**
1. **Spec gap:** the spec gave starting balances (BR-1) but not when they are created. Added `register_employee` and updated the spec (v1.1 change log).
2. **Known limitation:** the in-memory repository saves the request and the balance in two separate calls, so a crash between them could leave them out of step. Accepted for Capstone 1; Capstone 3 wraps both in one database transaction.


---

## Entry 5 — Notifications (Day 1, tasks T10–T11)

**Prompt:** Implement notifications.py (abstract Notifier, EmailNotifier stub, InAppNotifier, concurrent send_all with asyncio.gather) and connect it to LeaveService so every submit, approve, reject and cancel sends its notifications.

**Generated:** A Notifier ABC using the template method pattern (send = delay + deliver + log), two channels, a send_all function using asyncio.gather with return_exceptions=True, and an async `_emit` in LeaveService that stores and then sends.

**Checked / changed:**
- Timed 4 sends of 0.2 s: 0.80 s one at a time vs 0.20 s with asyncio.gather (AC-9.2), both standalone and inside `apply`.
- Checked the recipients for every event against BR-7 (AC-9.1, AC-9.3) and that new notifications arrive unread.
- With a channel that always fails, the request is still saved as pending, the balance holds 3 days, the failures are logged, and in-app delivery still works (AC-9.4).
- Checked that every `_emit` call is awaited; a missing `await` would silently skip sending.

**Issues caught:**
1. **Confusing AI edit instructions:** the step-by-step edit for service.py contradicted itself about where to place the new import, so the import ended up out of alphabetical order and the linter flagged the whole import block. Switched to replacing the complete file, which put the imports in the correct order.


---

## Entry 6 — Demo script and pytest tests (Day 1, tasks T12–T13)

**Prompt:** Write `leavedesk/demo.py` that runs the happy path and every SPEC edge case with a ✓/✗ checklist, then a pytest suite covering every acceptance criterion, including failure paths.

**Generated:** A demo with a Checklist helper, a fresh service per edge case, a fixed "today" and a non-zero exit status on failure; pytest configuration in pyproject.toml; requirements-dev.txt; shared fixtures; 77 tests across 7 files.

**Checked / changed:**
- Ran the demo: 32/32 checks passed, exit status 0. Confirmed EC-1 to EC-5 each raise the error named in SPEC 9.1 (the Capstone 1 "Done when").
- Ran pytest: 77 passed. Changed one expected value (3 to 4 working days) to confirm a test really fails and reports the values, then changed it back.
- Checked that failure-path tests also assert nothing changed (for example the balance stays 18 after a refused request).
- Checked that `except expected` comes before `except Exception` in the demo's `raises()` helper; the other order would mark every correct error as a failure.

**Issues caught:**
1. **Missing tests went unnoticed until counted:** the first pytest run collected 16 tests instead of 25, because test_models.py had been created but not saved. Caught by comparing the collected count with the expected count. Turned on VS Code Auto Save.
2. **Known risk:** the concurrency test asserts that 4 sends of 0.2 s finish in under 0.4 s. On a very slow machine this could fail occasionally; the margin is twice the expected time to keep that unlikely.


---

## Entry 7 — REST API (Capstone 2, tasks A2–A11)

**Prompt:** Implement API_SPEC.md: FastAPI app factory, pydantic-settings, Argon2id hashing, JWT auth, the error contract, request-ID middleware, leave and notification routes, BackgroundTasks sending, an SSE stream, then tests for API-1 to API-28 and Ruff.

**Generated:** The `leavedesk/api` package (13 files), two domain additions (repository notification methods, Inbox), 40 API tests with a mocked notifier and signed-in user fixtures, and Ruff settings.

**Checked / changed:**
- Smoke-tested with curl: health, generic login error, 201 on apply with `X-Request-ID`, balances returned as strings.
- Security review of the generated code: `jwt.decode` pins `algorithms=[...]` (blocks algorithm-swap attacks); unknown emails are checked against a dummy Argon2 hash so failed logins take the same time; the login error text is identical for both failure cases; `employee_id` is taken from the token, never the body (tested); `.env` is git-ignored and tests never read it.
- Confirmed BackgroundTasks really defer sending: a unit test shows one task is queued and nothing is sent until the task runs.
- 117 tests pass; `ruff check` and `ruff format --check` are clean.

**Issues caught:**
1. **Wrong code in the wrong file:** `/auth/login` returned 404. Listing the registered routes from `/openapi.json` and comparing line counts showed the leave-route code had been pasted into `routes/auth.py`. Fixed and re-verified.
2. **Dependency file contents:** the Day 1 approach (`pip freeze > requirements.txt`) would now ship pytest and Ruff into the production image. Changed `requirements.txt` to the app's runtime libraries only, with test tools in `requirements-dev.txt`.
3. **Browser limitation found while specifying the stream:** EventSource cannot send an Authorization header, so the stream also accepts `?access_token=`. To stop tokens reaching logs, the middleware logs the path without the query string.
4. **Deprecation warning:** Starlette warns that its TestClient is moving from httpx to httpx2. Filtered that single warning in pyproject.toml so test output stays clean; follow-up: switch to httpx2 once FastAPI's TestClient supports it.
5. **Files missing from the pushed branch:** a typo in `.env.example`'s file name made one `git add` command fail completely, so `inbox.py` and `.env.example` were never committed although tests passed locally. Caught by reading `git status` after pushing; confirmed fixed by cloning the branch into a fresh folder and running the full test suite there.


---

## Entry 8 — Docker and Docker Compose (Capstone 2, task A12)

**Prompt:** Write a Dockerfile for the API and a docker-compose.yml with api and db (PostgreSQL) services so that `docker compose up` serves Swagger at /docs on a clean machine.

**Generated:** Dockerfile (python:3.12-slim, non-root user, health check), .dockerignore, docker-compose.yml (api + postgres:17 with a health check and a named volume), POSTGRES_PASSWORD in .env.example, README quick start.

**Checked / changed:**
- Both containers report healthy; `/health` returns ok; Swagger login works with the demo users.
- Inside the container: /app holds only `leavedesk` and `requirements.txt` (no `.env`, no `tests`), and the process runs as `appuser`, not root.
- `docker compose down -v` then `up --build` (no cached database) works, simulating a clean machine.

**Issues caught:**
1. **Missing .dockerignore:** the build log showed `.dockerignore` transferring only 2 bytes: the file had not been created, and the failed `git add` also meant nothing was committed (GitHub rejected the PR with "No commits between main and feature/docker"). The image itself was safe, because the Dockerfile copies only `requirements.txt` and `leavedesk/`, but `.env` was still being sent to Docker as part of the build context. Created `.dockerignore` and confirmed the build context step now reads it.
2. **Unpinned database image:** `postgres` (latest) can jump a major version and change its data layout; pinned `postgres:17`.


---

## Entry 9 — Capstone 3 spec: SPEC.md v1.3, API_SPEC.md v1.1, SCHEMA.md (task T14)

**Prompt:** Plan Capstone 3 (PostgreSQL) from the workshop plan, then write the spec first: business rules and Given/When/Then criteria for the database work, the API contract changes, and a SCHEMA.md justifying keys, lookup table vs ENUM vs CHECK, `numeric(5,1)` and `timestamptz`.

**Generated:** A 13-step plan; SPEC.md section 12 (FR-12 to FR-18, DB-1 to DB-34) and BR-9 to BR-13; API_SPEC.md v1.1 (Idempotency-Key, If-Match and `version`, keyset pagination, three new error codes, outbox delivery); SCHEMA.md (12 tables, constraints, ERD, index plan, roles, migrations, review checklist).

**Checked / changed:**
- Compared every Capstone 3 bullet in the workshop plan (Parts A, B, C, C2, D and "Done when") with the spec; each one maps to at least one DB-n criterion or a SCHEMA.md section.
- Checked that every new API feature is additive, so API-1 to API-28 can pass unchanged: new fields (`version`, `next_cursor`), optional headers, and `offset` still working. Searched the Day 2 tests for exact-dictionary comparisons of responses that a new field would break; none compare a whole `LeaveRequestOut`.
- Asked the trainer whether the repository may change from sync to async. Answer: async for I/O such as API calls and background work, sync for plain logic, and changing Capstone 1–2 code to fit is fine. Database queries are I/O, so the repository becomes async (task T15).

**Issues caught:**
1. **AI recommendation that ignored the requirement:** the first plan suggested keeping the domain's text ids (`LR-1a2b3c4d`) as primary keys. The workshop plan asks to justify *identity vs UUIDv7*, and text ids are neither. Changed to identity primary keys with a separate `public_id` column, so the API is unchanged and the required comparison is answered in SCHEMA.md 2.1.
2. **AI reasoning that didn't match the trainer:** the first plan recommended a sync SQLAlchemy session to avoid changing the repository interface. The trainer's guidance (async for I/O, changes allowed) removed that reason; switched to `AsyncSession`.
3. **Plan item that broke a requirement:** the first plan listed the outbox worker as something to cut if time was short, but the workshop plan names the worker as a requirement. Removed it from the cut list.
4. **Index plan that would have defeated the "Done when":** foreign key indexes required by Part A (on `leave_requests.employee_id`) would already serve two of the three PERF queries, so their "before" plans would never show a sequential scan. Documented the method in SCHEMA.md 5.2: capture "before" plans with the index dropped inside a rolled-back transaction (PostgreSQL DDL is transactional), and replace the single-column FK index with the composite history index, which also covers the foreign key.
5. **Notifications needed earlier than planned:** the first plan put the `notifications` table in a later revision, but the Day 2 notification tests must pass on PostgreSQL as soon as the repository is swapped in. Moved `notifications` into revision 0001; only the outbox comes later.


---

## Entry 10 — Async repository (Capstone 3, task T15)

**Prompt:** Make the `LeaveRepository` interface async so a PostgreSQL implementation can await the database, keep everything else working on the in-memory repository, and add the `lock` keyword from SPEC BR-10.

**Generated:** Async versions of `LeaveRepository`, `InMemoryLeaveRepository`, `Inbox`, the storage-touching `LeaveService` methods (`register_employee`, `get_balances`, `list_notifications` and helpers), API dependencies and routes, the demo and the test helpers; demo-data seeding moved into a FastAPI lifespan; a new `tests/test_locking.py`.

**Checked / changed:**
- Ran the full suite before changing anything (117 passed) and after (120 passed: the original 117 unchanged in meaning plus 3 new lock-order tests). The Day 2 API test files needed no edits.
- `python -m leavedesk.demo` still passes 32/32; `ruff check` and `ruff format --check` are clean.
- Started the real server with uvicorn and checked login, a balance read and a wrong-password 401 with curl, which proves the lifespan seeding runs outside the tests too.
- Kept the pure rules (dates, policies, balance arithmetic, Pydantic validation) synchronous, following the trainer's guidance: async only for code that waits on I/O.

**Issues caught:**
1. **Hidden event-loop blocking:** making `/auth/login` an `async def` (needed to await the repository) would have run Argon2id, which is deliberately slow, directly on the event loop, freezing every other request during each login. The old sync route ran in FastAPI's thread pool automatically. Fixed by calling `verify_password` through `run_in_threadpool`.
2. **Seeding could no longer run in the factory:** `create_app` is a plain function, so it cannot `await register_employee`. Moved seeding into a lifespan handler, which both uvicorn and `with TestClient(app)` run before the first request.
3. **Clumsy generated test code:** the AI's first edit of `tests/test_service.py` produced `assert ((await annual(service)).pending, (await annual(service)).available) == ...`, which reads the balance twice. Rewritten to read it once into a variable.
4. **Known follow-up:** the Day 2 test for API-28 calls `users.find_by_email()` synchronously, so the user store stays sync in this step. Step 5 (PostgreSQL users) must keep that method callable without `await`, or that unchanged test breaks.


---

## Entry 11 — Database infrastructure, models and revision 0001 (Capstone 3, tasks T16–T17)

**Prompt:** Add SQLAlchemy 2 (async), psycopg 3 and Alembic; a Docker init script for the migrator and app roles with timeouts and a test database; SQLAlchemy models for SCHEMA.md tables 4.1–4.10; revision 0001 with the EXCLUDE constraint, append-only ledger and seed rows; tests for the database rules.

**Generated:** `leavedesk/db/` (base with a naming convention, models, engine), `alembic.ini`, `migrations/` (env.py and revision 0001), `docker/postgres-init/01-roles.sh`, `tests/db/` (17 tests), and changes to `docker-compose.yml` (`migrate` service, database published on localhost only), `Dockerfile`, `.env.example`, settings, requirements and README.

**Checked / changed:**
- Drafted the table commands with `alembic revision --autogenerate`, then reviewed them line by line against SCHEMA.md before adding the hand-written parts.
- Ran on a real PostgreSQL: `alembic upgrade head`, `alembic check` ("No new upgrade operations detected"), `downgrade base`, `upgrade head`, `check` again (DB-3).
- `pytest tests/db`: 17 passed (DB-3 to DB-6, DB-8, DB-14, DB-29, DB-30, plus seed, balance-limit, per-employee overlap and version-column tests). Without the test URLs, the same tests are skipped and the other 120 still pass.
- `docker compose config` validates the Compose file.

**Issues caught:**
1. **`alembic check` cannot see the EXCLUDE constraint.** Constraints written with `op.execute` are invisible to autogenerate, so "models match the database" says nothing about them. That is why DB-6 tests the overlap rule directly in SQL.
2. **Migrations would have required the JWT secret:** reusing the API's `Settings` in `env.py` makes Alembic fail without `JWT_SECRET` and `DEMO_PASSWORD`. Added a small `MigrationSettings` that reads only `MIGRATION_DATABASE_URL`.
3. **A `%` in a password breaks Alembic's config:** `Config.set_main_option` uses configparser, which treats `%` as special. The test fixture doubles it; `.env.example` also recommends letters and digits only.
4. **The plan said "grants in the revision", which would mean repeating `GRANT` in every future revision.** Switched to `ALTER DEFAULT PRIVILEGES` in the init script, so new tables are usable automatically and revisions only revoke. Updated SCHEMA.md to v1.1 to match the code.
5. **TRUNCATE bypasses row triggers:** the append-only trigger does not stop `TRUNCATE`. Confirmed the app role has no `TRUNCATE` privilege (default privileges grant only SELECT/INSERT/UPDATE/DELETE) and documented it in SCHEMA.md 4.8.
6. **Silent N+1 risk:** relationships default to lazy loading, which in async SQLAlchemy fails with a confusing `MissingGreenlet` error, and in sync code silently issues one query per row. Every relationship is `lazy="raise"`, so a missing `selectinload` fails at once with a clear message.
7. **Init scripts run only once:** the postgres image runs `/docker-entrypoint-initdb.d` only on an empty data volume, so an existing Capstone 2 volume would never get the roles. README and the Compose header say to run `docker compose down -v` first.
8. **Optimistic locking was silently switched off (the most serious one):** the generated models had `__mapper_args__ = {"version_id_col": "version"}`. SQLAlchemy accepted the string without any error or warning, but `mapper.version_id_col` stayed the string `"version"` instead of the column, so no version check would ever happen and DB-12/DB-13 could never pass. Found by inspecting the configured mapper. Fixed by referencing the column object (`{"version_id_col": version}`, placed after the column), and added `test_version_columns_are_wired_for_optimistic_locking`, confirmed to fail with the old line and pass with the fix.
9. **Port clash found only on the real machine:** on the Mac, `docker compose up -d db` failed with "address already in use" on 5432, and Alembic then reached a *different* PostgreSQL (version 18, installed in August with the postgresql.org installer, running as the `postgres` user), so the error looked like a wrong password. Plain `lsof` showed nothing because that server belongs to another macOS user; `ps aux` and `sudo lsof` found it. Fixed by publishing the Docker database on host port 5433 (containers still use `db:5432`) and updating `.env.example` and the README to match. Lesson: "password authentication failed" can mean "connected to the wrong server".


---

## Entry 12 — PostgreSQL repository and wiring (Capstone 3, task T18)

**Prompt:** Implement `PostgresLeaveRepository` behind the existing async `LeaveRepository` interface, store logins in the database, open one session and transaction per request, translate database errors into domain errors, and make the unchanged Day 2 tests pass on PostgreSQL.

**Generated:** `leavedesk/db/repository.py`, `leavedesk/db/users.py`, `RepoDep` in `leavedesk/api/deps.py`, PostgreSQL mode in `create_app`, `ConcurrentUpdateError` (409), `save_balance(..., request_id=)` so ledger rows name their request, a repo-root `conftest.py` and `scripts/pytest-postgres.sh`, and `tests/db/test_repository.py` (DB-2, DB-9, DB-13, EXCLUDE mapping, N+1).

**Checked / changed:**
- `pytest`: 142 passed in memory. `scripts/pytest-postgres.sh`: the same 142 passed on PostgreSQL, including the 40 Day 2 API test files, which are unchanged (DB-1).
- Confirmed the API tests really used PostgreSQL by reading the ledger rows a test left behind: grant, reserve and confirm rows, each linked to its request, exactly as SCHEMA.md 4.8 describes.
- Ran uvicorn against PostgreSQL: applied, approved, restarted the server, and the request was still approved; start-up logged `demo_data=already present` on the second run.

**Issues caught:**
1. **The unchanged Day 2 tests caught a contract change:** `numeric(5,1)` returns `Decimal("3.0")`, so balances came back as `"3.0"` instead of `"3"`. The obvious fix, `Decimal.normalize()`, turns `10.0` into `1E+1`; used a helper that keeps whole numbers whole and half days as `x.5`.
2. **Commit timing:** a normal `yield` dependency in FastAPI finishes *after* the response is sent, so a client could get `201` for a change whose commit later failed, or read stale data with its next request. Used `Depends(get_repository, scope="function")`, which commits before the response (FastAPI 0.121+; requirements pinned).
3. **Autoflush skipped the error translation:** `save_request` changed the row and then looked up the decider's id. That lookup is a query, SQLAlchemy flushed first, and the version check raised `StaleDataError` outside the `try`, as a 500 instead of 409. Found by the DB-13 test; fixed by doing every lookup before changing the row.
4. **Seeding twice:** with a database, the start-up seeding would try to register the demo employees again on every restart. Made it check first (DB-2 also covers this).
5. **Async rule vs a blocking call:** the login lookup uses a small sync connection pool, run in the thread pool together with Argon2id, which keeps the event loop free and keeps the unchanged API-28 test (which calls `find_by_email()` without `await`) working. Documented in `leavedesk/db/users.py`.
6. **Safety of the test reset:** the reset empties tables, so it refuses to run unless `DATABASE_URL` names a database ending in `_test`.


---

## Entry 13 — Safe approvals (Capstone 3, task T19)

**Prompt:** Make approvals safe under concurrency: one transaction with row locks (request, then balance), a `version` with an optional `If-Match` header (409 on a mismatch), 503 `DATABASE_BUSY` for lock and statement timeouts, and tests that fire two actions at the same moment, including a way to show the test failing without the locks.

**Generated:** `version` on `LeaveRequest` and `LeaveRequestOut`; `expected_version` on approve/reject/cancel; the `If-Match` header; a `DBAPIError` handler (55P03, 57014, 40P01 -> 503 with `Retry-After`); `tests/db/test_concurrency.py` (DB-7, DB-10, DB-11, DB-15, DB-16 switch), `tests/api/test_versions_api.py` (DB-12, runs in both storage modes), `tests/db/support.py`.

**Checked / changed:**
- 152 passed in memory and 152 on PostgreSQL. `tests/db/test_concurrency.py` run five times in a row: all green each time.
- `LEAVEDESK_DEMO_NO_LOCKS=1 pytest tests/db/test_concurrency.py -k db10` fails with "both approvals went through"; without the switch it passes. This is the review demo.
- DB-15 really waits the app role's 2-second `lock_timeout`, then gets 503, and the request was rolled back (nothing listed).

**Issues caught:**
1. **A concurrency test that proved nothing:** the first DB-7 test (two overlapping submits at once) passed, but only because the balance lock made the two submits take turns, so the ordinary Python overlap check refused the second one. The EXCLUDE constraint was never exercised. Fixed by using two leave types (different balance rows, so the locks don't serialise them) and asserting on the message that only the EXCLUDE translation produces.
2. **A flaky test:** even then, DB-7 depended on both submits running their overlap check before either saved, which is usual but not guaranteed, so it could fail now and then. A barrier in a test-only repository subclass forces that order, making the test deterministic (5/5 runs).
3. **The demo needed the worst timing on purpose:** the unsafe repository waits on a barrier after reading, so both "managers" read the old values before either writes. Without it, the bug might not show up during the live demo.
4. **An unsafe demo with half the protection still on:** turning off only the row lock would not show the bug, because the version check alone stops the second approval (with a 409). The demo repository writes with plain UPDATEs (no version check) to show the real lost-update bug; the regular code keeps both layers.
