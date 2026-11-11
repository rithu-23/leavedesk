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
