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
