# LeaveDesk — Specification

**Version:** 1.5 (Capstone 4) · **Status:** Draft · **Author:** Rithu

Companion documents: `API_SPEC.md` (REST contract), `SCHEMA.md` (database design) and `UI_SPEC.md` (web app).

---

## 1. Purpose

LeaveDesk lets employees apply for leave and lets managers approve or reject it.
It keeps every employee's leave balance correct and notifies the right people at each step.

## 2. Scope

### 2.1 In scope (Capstone 1)
- Leave rules written in plain Python, in the domain package `leavedesk/domain/`.
- In-memory storage only (data lives in Python lists and dictionaries while the program runs).
- Notifications sent through a stub email channel and an in-app channel.
- A demo script, `python -m leavedesk.demo`, that runs the happy path and every edge case.

### 2.2 Out of scope (Capstone 1)
- Web API (Capstone 2), database (Capstone 3), user interface (Capstone 4).
- Login and passwords (Capstone 2).
- Public holidays: only Saturdays and Sundays are non-working days.
- Carrying unused leave into the next year.
- Splitting a half day into morning and afternoon.

### 2.3 In scope (Capstone 3)
- PostgreSQL storage through SQLAlchemy 2 (async, psycopg 3) and Alembic migrations, behind the same `LeaveRepository` interface. The in-memory repository stays for fast domain tests.
- The database enforces the leave rules it can: date checks, overlap (EXCLUDE constraint), balance limits, uniqueness (see `SCHEMA.md`).
- Safe concurrent actions: row locks, optimistic locking with a version column, idempotent submit.
- Notifications stored in the database and delivered through a transactional outbox, a `SKIP LOCKED` worker and `LISTEN/NOTIFY`.
- Login lockout, separate migration and app database roles, query timeouts.
- Indexes proven with `EXPLAIN (ANALYZE, BUFFERS)` on about 100,000 seeded requests (`PERF.md`), and keyset pagination.

### 2.4 Out of scope (Capstone 3)
- More than one tenant at run time: every table carries `tenant_id`, but the app runs a single tenant (`T-DEMO`, from the `TENANT_ID` setting).
- Refresh tokens, password reset, rate limiting by IP address.
- Backups, restore tests and data masking (take-home topics in the workshop plan).
- Row-level security (stretch goal only).

---

## 3. Entities

### 3.1 Employee
| Field | Type | Rules |
|---|---|---|
| `id` | text | Required, unique |
| `name` | text | Required, 1–100 characters |
| `email` | text | Required, must look like an email address (`name@domain.tld`) |
| `role` | `employee` or `manager` | Required |
| `manager_id` | text or none | The `id` of this person's manager. Empty only for someone with no manager. |

### 3.2 Manager
A Manager is an Employee whose `role` is `manager`. Managers can also apply for leave themselves.

**Design decision:** Manager is a *role field*, not a separate subclass of Employee. A person's role can change (an employee gets promoted) without changing what kind of object they are, and a manager still needs every employee ability (applying for leave).

### 3.3 LeaveType
One of: `ANNUAL`, `SICK`, `CASUAL`.

### 3.4 LeaveRequest
| Field | Type | Rules |
|---|---|---|
| `id` | text | Required, unique |
| `employee_id` | text | Required, must belong to an existing employee |
| `leave_type` | LeaveType | Required |
| `start_date` | date | Required |
| `end_date` | date | Required, not before `start_date` |
| `half_day` | yes/no | Default no. Allowed only when `start_date` equals `end_date` |
| `reason` | text | Required, 10–500 characters after trimming spaces |
| `status` | `pending`, `approved`, `rejected` or `cancelled` | Default `pending` |
| `days` | decimal number | Working days the request uses, in steps of 0.5. Calculated by the system, never typed in |
| `created_at` | date and time (UTC) | Set by the system |
| `decided_by` | text or none | `id` of the manager who approved or rejected it |
| `decision_note` | text or none | Required when rejecting (the rejection reason) |

### 3.5 LeaveBalance
One balance per employee per leave type.

| Field | Type | Meaning |
|---|---|---|
| `employee_id` | text | Whose balance this is |
| `leave_type` | LeaveType | Which kind of leave |
| `entitlement` | decimal | Days given for the year |
| `used` | decimal | Days in approved requests |
| `pending` | decimal | Days in requests still waiting for a decision |
| `available` | decimal (calculated) | `entitlement − used − pending` |

### 3.6 Notification
| Field | Type | Rules |
|---|---|---|
| `id` | text | Required, unique |
| `recipient_id` | text | The employee who receives it |
| `event` | `submitted`, `approved`, `rejected` or `cancelled` | What happened |
| `message` | text | Human-readable message |
| `read` | yes/no | Default no |
| `created_at` | date and time (UTC) | Set by the system |

---

## 4. Business rules

### BR-1 Entitlements
Each employee starts the year with: **Annual 18 days, Sick 12 days, Casual 6 days.**

### BR-2 Counting leave days
- Monday to Friday count as working days. Saturdays and Sundays are not counted.
- The start and end dates are both included.
- A half-day request counts as **0.5** days. It must be a single date, and that date must be a working day.
- A request must use at least 0.5 working days. For example, a Saturday-to-Sunday request is invalid.

### BR-3 Leave policies (rules that differ by leave type)
| Leave type | Rule |
|---|---|
| Annual | Cannot start before today. |
| Sick | May start up to 7 calendar days before today (sickness is often reported afterwards). |
| Casual | Cannot start before today. At most 2 working days per request. |

All leave types must also pass the balance check (BR-4).

### BR-4 Balance accounting
| Action | Effect on the balance |
|---|---|
| Apply | Allowed only if `available ≥ days`; then `pending` increases by `days` |
| Approve | `pending` decreases by `days`; `used` increases by `days` |
| Reject or cancel | `pending` decreases by `days` |

`available` can never become negative.

### BR-5 No overlapping leave
A new request is refused if any of its dates overlap an existing **pending** or **approved** request of the same employee, whatever the leave type (half days included).
Rejected and cancelled requests are ignored.
Two date ranges overlap when `new.start ≤ existing.end` **and** `existing.start ≤ new.end`.

### BR-6 Status lifecycle
```text
              approve (manager)
          ┌──────────────────────► approved
          │
 pending ─┼─── reject (manager, note required) ──► rejected
          │
          └──── cancel (owner) ──► cancelled
```
| Action | Allowed from | Who may do it |
|---|---|---|
| Approve | `pending` only | The requester's manager |
| Reject | `pending` only, with a `decision_note` | The requester's manager |
| Cancel | `pending` only | The employee who made the request |

- Any other change, for example approving a rejected request, is an **invalid transition**.
- An action by the wrong person, for example a manager approving someone else's report, is **not authorised**. Managers therefore cannot approve their own requests.

### BR-7 Who gets notified
| Event | Recipients | Example message |
|---|---|---|
| `submitted` | The employee's manager (action needed) and the employee (confirmation) | "Ana requested 3 days of annual leave (12–14 Nov)." |
| `approved` | The employee | "Your annual leave (12–14 Nov) was approved." |
| `rejected` | The employee | "Your annual leave (12–14 Nov) was rejected: team deadline." |
| `cancelled` | The employee's manager | "Ana cancelled her annual leave request (12–14 Nov)." |

- Each recipient is notified through every notifier (email stub and in-app).
- All sends for one event happen **concurrently** (at the same time, using `asyncio.gather`).
- A failed send is logged, but it does **not** undo the leave action.

### BR-8 Audit and timing
- Every LeaveService action is logged: the action name, the request involved, and whether it succeeded or failed.
- The duration of each action is measured and logged.
- From Capstone 3, each successful state change also writes an `audit_log` row in the same database transaction (SCHEMA.md 4.9).

### BR-9 Storage keeps the rules (Capstone 3)
- The database rejects data that breaks a rule even if the application has a bug: end date before start date, a half day across two dates, a reason outside 10–500 characters, an unknown status, a day count that is not a whole or half number, `used + pending` above the entitlement, and a duplicate email (case-insensitive) within a tenant.
- Two pending or approved requests of the same employee can never overlap, even when they are submitted at the same moment (EXCLUDE constraint).
- Every balance movement is recorded in an append-only ledger. For each employee and leave type, the stored balance always equals the sum of the ledger movements (BR-4 table, SCHEMA.md 2.6).

### BR-10 Concurrent actions are safe (Capstone 3)
- Each action (apply, approve, reject, cancel, mark read) runs in one database transaction: either every change is saved or none is.
- Approve, reject and cancel lock the request and then its balance; apply locks the balance. Locks are always taken in that order.
- Each request and balance has a `version` number that goes up by one on every change. A change based on an older version is refused with `ConcurrentUpdateError`.
- A client may send the request's version with approve, reject or cancel (`If-Match`); if it no longer matches, the action is refused with `ConcurrentUpdateError` and nothing changes.
- A query that runs longer than 5 seconds, or waits more than 2 seconds for a lock, is stopped and the action fails with `DatabaseBusyError`; nothing is saved.

### BR-11 Submitting is idempotent (Capstone 3)
- A client may send an `Idempotency-Key` (1–255 characters) when submitting a request.
- The same employee repeating the same key with the same body gets the first result again; no second request is created and no extra days are reserved.
- Repeating a key with a different body is refused with `IdempotencyKeyReusedError`.
- A submit that fails stores nothing, so it can be retried with the same key. Keys are scoped to one employee.

### BR-12 Notifications are never lost or phantom (Capstone 3)
- The notification rows for an action and their outbox entries are saved in the same transaction as the action. If the action is rolled back, no notification exists and nothing is sent.
- Each outbox entry is sent exactly once, even with several workers running. A failed send is retried up to 5 times with a growing delay, then marked `failed`; the leave action is never undone (BR-7 still holds).
- When a notification is saved, the recipient's open stream receives it straight away (`LISTEN/NOTIFY`), without polling.
- From Capstone 3, `submitted` notifications go through the outbox too, so every BR-7 event follows the same path.

### BR-13 Login lockout (Capstone 3)
- After 5 wrong passwords in a row, the account is locked for 15 minutes (`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCK_MINUTES`).
- While locked, every login attempt, even with the right password, gets the same generic error as a wrong password, so an attacker cannot tell whether an account exists or is locked.
- A successful login resets the count. Unknown emails take the same time and give the same error.

---

## 5. Assumptions
- "Today" is given to LeaveService from outside rather than read from the computer clock, so the demo and tests give the same results on any day.
- Each employee has at most one manager.
- All requests fall within a single leave year.
- Capstone 3 runs a single tenant (`T-DEMO`); multi-tenant data is supported by the schema, not by the API.

---

## 6. Example data used in the acceptance criteria

| Item | Value |
|---|---|
| Today | **Monday 9 Nov 2026** |
| Ana | role `employee`, manager is Mo |
| Mo | role `manager` (Ana's manager) |
| Lee | role `manager` (not Ana's manager) |
| Starting balances | Everyone starts with BR-1 entitlements: Annual 18, Sick 12, Casual 6; nothing used or pending |

Calendar for reference: Fri 6, **Mon 9**, Tue 10, Wed 11, Thu 12, Fri 13, *Sat 14, Sun 15*, Mon 16, Tue 17, Wed 18, Thu 19, Fri 20 Nov 2026.

---

## 7. Functional requirements and acceptance criteria

Each requirement lists its happy path first, then its failure paths.
Error names refer to the error catalogue in section 8.

### FR-1 Apply for leave (BR-2, BR-4)
An employee can submit a leave request; the system works out how many working days it uses and reserves them from the balance.

| ID | Given | When | Then |
|---|---|---|---|
| AC-1.1 *(happy path)* | Ana has 18 annual days available | She applies for annual leave Wed 11 – Fri 13 Nov, reason "Family trip to Ooty" | The request is saved as `pending` with `days = 3`; her annual balance shows `pending = 3`, `available = 15` |
| AC-1.2 | Ana has 18 annual days available | She applies for annual leave Fri 13 – Mon 16 Nov | `days = 2` (Sat 14 and Sun 15 are not counted) |
| AC-1.3 | Ana has 18 annual days available | She applies for a half day of annual leave on Tue 17 Nov | `days = 0.5`; `available = 17.5` |
| AC-1.4 | — | Ana applies for leave Sat 14 – Sun 15 Nov | `InvalidLeaveRequestError` (no working days); nothing is saved |

### FR-2 Validate request input (section 3.4)
Badly formed input is refused before any business rule runs.

| ID | Given | When | Then |
|---|---|---|---|
| AC-2.1 | — | A request is created with end date Wed 11 Nov before start date Fri 13 Nov | `ValidationError` naming the end date |
| AC-2.2 | — | A request is created with reason "trip" (under 10 characters) | `ValidationError` naming the reason |
| AC-2.3 | — | A request is created with `half_day = yes` from Wed 11 to Thu 12 Nov | `ValidationError` (half day must be a single date) |
| AC-2.4 | — | A request is created with status `on_hold` | `ValidationError` (not an allowed status) |

### FR-3 Apply leave-type policies (BR-3)
Each leave type enforces its own rule.

| ID | Given | When | Then |
|---|---|---|---|
| AC-3.1 | Today is Mon 9 Nov | Ana applies for annual leave starting Fri 6 Nov | `InvalidLeaveRequestError` (annual leave cannot start in the past) |
| AC-3.2 *(happy path)* | Today is Mon 9 Nov | Ana applies for sick leave Mon 2 – Tue 3 Nov (7 days back) | Accepted as `pending`, `days = 2` |
| AC-3.3 | Today is Mon 9 Nov | Ana applies for sick leave starting Fri 30 Oct (10 days back) | `InvalidLeaveRequestError` (sick leave can be backdated by 7 days at most) |
| AC-3.4 | Ana has 6 casual days | She applies for casual leave Wed 18 – Fri 20 Nov (3 working days) | `InvalidLeaveRequestError` (casual leave is at most 2 days per request) |

### FR-4 Prevent overlapping leave (BR-5)

| ID | Given | When | Then |
|---|---|---|---|
| AC-4.1 | Ana has a `pending` annual request Wed 11 – Fri 13 Nov | She applies for sick leave on Fri 13 Nov | `OverlappingLeaveError`; her balances are unchanged |
| AC-4.2 | Ana's request Wed 11 – Fri 13 Nov was `cancelled` | She applies for annual leave Wed 11 – Fri 13 Nov again | Accepted as `pending` (cancelled requests are ignored) |

### FR-5 Enforce the balance (BR-4)

| ID | Given | When | Then |
|---|---|---|---|
| AC-5.1 | Ana has 18 annual days available | She applies for annual leave Mon 16 Nov – Fri 11 Dec (20 working days) | `InsufficientBalanceError`; her balance is unchanged |
| AC-5.2 | Ana has a `pending` 15-day annual request, so `available = 3` | She applies for 4 more annual days | `InsufficientBalanceError` (pending days count against the balance) |

### FR-6 Approve a request (BR-4, BR-6)

| ID | Given | When | Then |
|---|---|---|---|
| AC-6.1 *(happy path)* | Ana has a `pending` 3-day annual request | Mo approves it | Status is `approved`, `decided_by = Mo`; annual balance shows `used = 3`, `pending = 0`, `available = 15` |
| AC-6.2 | Ana has a `pending` request | Lee (not her manager) approves it | `NotAuthorisedError`; the request stays `pending` |
| AC-6.3 | Ana's request is already `approved` | Mo approves it again | `InvalidTransitionError` |

### FR-7 Reject a request (BR-4, BR-6)

| ID | Given | When | Then |
|---|---|---|---|
| AC-7.1 *(happy path)* | Ana has a `pending` 3-day annual request | Mo rejects it with note "Team deadline that week" | Status is `rejected`, `decision_note` is saved; annual balance returns to `pending = 0`, `available = 18` |
| AC-7.2 | Ana has a `pending` request | Mo rejects it without a note | `InvalidLeaveRequestError` (a rejection needs a reason); the request stays `pending` |
| AC-7.3 | Ana's request is already `approved` | Mo rejects it | `InvalidTransitionError` |

### FR-8 Cancel a request (BR-4, BR-6)

| ID | Given | When | Then |
|---|---|---|---|
| AC-8.1 *(happy path)* | Ana has a `pending` 3-day annual request | Ana cancels it | Status is `cancelled`; annual balance returns to `available = 18` |
| AC-8.2 | Ana has a `pending` request | Mo tries to cancel it | `NotAuthorisedError` (only the owner can cancel) |
| AC-8.3 | Ana's request is `approved` | Ana tries to cancel it | `InvalidTransitionError` (only pending requests can be cancelled) |

### FR-9 Send notifications (BR-7)

| ID | Given | When | Then |
|---|---|---|---|
| AC-9.1 *(happy path)* | Email and in-app notifiers are configured | Ana submits a request | Two notifications are created, one for Mo and one for Ana, each sent through both notifiers (4 sends) |
| AC-9.2 | Each stub send takes 0.2 seconds | Ana submits a request (4 sends) | All sends finish in about 0.2 seconds in total, not 0.8, because they run concurrently |
| AC-9.3 | — | Mo approves, rejects, or Ana cancels a request | The recipients match BR-7 for that event, with `read = no` |
| AC-9.4 | The email notifier fails | Ana submits a request | The request is still saved as `pending`; the failure is logged; the in-app notification is still delivered |

### FR-10 View balances (section 3.5)

| ID | Given | When | Then |
|---|---|---|---|
| AC-10.1 *(happy path)* | Ana has one approved 3-day annual request and one pending half day | Her balances are requested | Annual shows `entitlement 18, used 3, pending 0.5, available 14.5`; Sick and Casual show their full entitlement |

### FR-11 Audit and timing (BR-8)

| ID | Given | When | Then |
|---|---|---|---|
| AC-11.1 *(happy path)* | — | Any LeaveService action succeeds | A log line records the action name, the request id, `success`, and the duration in milliseconds |
| AC-11.2 | — | A LeaveService action raises an error | A log line records the action name, `failed`, and the error name; the error still reaches the caller |

---

## 8. Error catalogue

All LeaveDesk errors inherit from one base error, `LeaveDeskError`, so callers can catch one specific error or all of them at once.

| Error | Raised by | When | HTTP status (API_SPEC.md 5) |
|---|---|---|---|
| `ValidationError` *(from Pydantic)* | Models | Input is badly formed (section 9.2) | 422 |
| `InvalidLeaveRequestError` | Policies, LeaveService | The request or action breaks a rule: no working days, policy rule (BR-3), half day on a weekend, rejection without a note | 422 |
| `InsufficientBalanceError` | LeaveService | `available` is less than the days requested (BR-4) | 422 |
| `OverlappingLeaveError` | LeaveService | The dates overlap a pending or approved request (BR-5) | 409 |
| `InvalidTransitionError` | LeaveService | The status change is not allowed (BR-6) | 409 |
| `NotAuthorisedError` | LeaveService | The person is not allowed to take this action (BR-6) | 403 |
| `NotFoundError` | Repository, LeaveService | An employee or request id does not exist | 404 |
| `ConcurrentUpdateError` *(Capstone 3)* | Repository, API | The row changed since it was read (stale `version` or `If-Match`) | 409 |
| `IdempotencyKeyReusedError` *(Capstone 3)* | API | An `Idempotency-Key` is repeated with a different body | 422 |
| `DatabaseBusyError` *(Capstone 3)* | Repository | `statement_timeout` or `lock_timeout` reached | 503 |

---

## 9. Edge cases and validation rules

### 9.1 Edge cases
The first five are required by the capstone and must appear in the demo.

| ID | Edge case | Expected result | Criteria |
|---|---|---|---|
| **EC-1** | End date before start date | `ValidationError` | AC-2.1 |
| **EC-2** | Weekends inside a date range | Weekend days are not counted | AC-1.2 |
| **EC-3** | Overlapping requests | `OverlappingLeaveError` | AC-4.1 |
| **EC-4** | Insufficient balance | `InsufficientBalanceError` | AC-5.1, AC-5.2 |
| **EC-5** | Half-day leave | Counts as 0.5 days; across two dates gives `ValidationError` | AC-1.3, AC-2.3 |
| EC-6 | Request covering only a weekend | `InvalidLeaveRequestError` | AC-1.4 |
| EC-7 | Half day on a Saturday or Sunday | `InvalidLeaveRequestError` | BR-2 |
| EC-8 | Annual leave in the past | `InvalidLeaveRequestError` | AC-3.1 |
| EC-9 | Sick leave exactly 7 days back vs 10 days back | Accepted vs `InvalidLeaveRequestError` | AC-3.2, AC-3.3 |
| EC-10 | Casual leave over 2 days | `InvalidLeaveRequestError` | AC-3.4 |
| EC-11 | Approval by someone who is not the requester's manager | `NotAuthorisedError` | AC-6.2 |
| EC-12 | Approving an already approved request | `InvalidTransitionError` | AC-6.3 |
| EC-13 | Rejecting without a note | `InvalidLeaveRequestError` | AC-7.2 |
| EC-14 | Cancelling an approved request | `InvalidTransitionError` | AC-8.3 |
| EC-15 | A notifier fails while sending | Action still succeeds; failure logged | AC-9.4 |
| EC-16 | Acting on a request id that does not exist | `NotFoundError` | Section 8 |

### 9.2 Validation rules (checked by the Pydantic models)
| Entity | Field | Rule |
|---|---|---|
| Employee | `id` | Not empty |
| Employee | `name` | 1–100 characters after trimming spaces |
| Employee | `email` | Matches `name@domain.tld` |
| Employee | `role` | `employee` or `manager` |
| LeaveRequest | `leave_type` | `ANNUAL`, `SICK` or `CASUAL` |
| LeaveRequest | `end_date` | Not before `start_date` |
| LeaveRequest | `half_day` | Only when `start_date` equals `end_date` |
| LeaveRequest | `reason` | 10–500 characters after trimming spaces |
| LeaveRequest | `status` | `pending`, `approved`, `rejected` or `cancelled` |

Rules that need other data (balance, overlap, policies, who may act) are checked by LeaveService, not by the models.

---

## 10. Task breakdown

| Task | What | Implements | File in `leavedesk/domain/` | Branch |
|---|---|---|---|---|
| T1 | Write this specification | All | `SPEC.md` (project root) | `docs/spec` |
| T2 | Custom exceptions with a `LeaveDeskError` base | Section 8 | `exceptions.py` | `feature/domain-models` |
| T3 | Pydantic models: Employee, LeaveRequest, Notification and enums, with validators | FR-2, section 9.2 | `models.py` | `feature/domain-models` |
| T4 | Working-day count and overlap check | BR-2, BR-5, FR-1, FR-4 | `dates.py` | `feature/domain-models` |
| T5 | `LeaveBalance` dataclass with `available` | BR-4, FR-5, FR-10 | `balance.py` | `feature/policies-service` |
| T6 | Abstract `LeavePolicy` with Annual, Sick and Casual subclasses | BR-3, FR-3 | `policies.py` | `feature/policies-service` |
| T7 | Repository interface and in-memory repository | Section 2.1 | `repository.py` | `feature/policies-service` |
| T8 | `@audit` decorator and timing context manager | BR-8, FR-11 | `instrumentation.py` | `feature/policies-service` |
| T9 | `LeaveService`: register employees (creates BR-1 balances), apply, approve, reject, cancel, get balances | BR-1, FR-1, FR-4 to FR-8, FR-10 | `service.py` | `feature/policies-service` |
| T10 | Abstract `Notifier` with `EmailNotifier` (stub) and `InAppNotifier` | BR-7, FR-9 | `notifications.py` | `feature/notifications` |
| T11 | LeaveService sends notifications concurrently with `asyncio.gather` | BR-7, FR-9 | `service.py` | `feature/notifications` |
| T12 | Demo script: happy path, EC-1 to EC-5 and the other edge cases | Section 11 | `leavedesk/demo.py` | `feature/demo` |
| T13 | pytest tests for the acceptance criteria | All FRs | `tests/` | `feature/demo` |

---

## 11. Definition of done (Capstone 1)
- `python -m leavedesk.demo` runs the happy path and all five required edge cases (EC-1 to EC-5), each failure raising the error named in this spec.
- Every acceptance criterion in section 7 is shown by the demo or a test.
- Work merged through pull requests with review comments; one merge conflict created and resolved in the history.
- `requirements.txt` and a README with venv setup steps are in the repository.

---

## 12. Capstone 3 requirements and acceptance criteria

The cast and "today" match section 6. "Directly in SQL" means a statement run against the database
without going through LeaveService, to prove the database itself enforces the rule. Tests marked
*(concurrent)* start two actions at the same time on separate database connections.

### FR-12 Durable storage (BR-9; Part A)

| ID | Given | When | Then |
|---|---|---|---|
| DB-1 *(happy path)* | Migrations at head, `DATABASE_URL` pointing at the test database | The unchanged Day 2 API test files run | All API-1 to API-28 pass, as they do on the in-memory repository |
| DB-2 | Ana has a pending request | The API process is restarted | The request and her balance are still there |
| DB-3 | An empty database | `alembic upgrade head`, then `downgrade base`, then `upgrade head` | Every step succeeds; the final schema matches the models (`alembic check` reports no changes) |

### FR-13 Rules enforced by the database (BR-9; Part A.3–A.5)

| ID | Given | When | Then |
|---|---|---|---|
| DB-4 | — | A request with end date 11 Nov and start date 13 Nov is inserted directly in SQL | Refused by a CHECK constraint (SQLSTATE `23514`) |
| DB-5 | Ana exists as `ana@leavedesk.test` | An employee with `ANA@LeaveDesk.test` is inserted in the same tenant; then in a second tenant | First refused (`23505`); second accepted |
| DB-6 | Ana has a pending request 11–13 Nov | An overlapping pending request (13 Nov) is inserted directly in SQL; then one overlapping a *cancelled* request | First refused by the EXCLUDE constraint (`23P01`); second accepted |
| DB-7 *(concurrent)* | Ana has no requests | Two `POST /leave-requests` for 11–13 Nov and 12–13 Nov arrive at the same time | Exactly one 201; the other 409 `OVERLAPPING_LEAVE`; one row in the database |
| DB-8 | A ledger row exists | The app role tries `UPDATE` and `DELETE` on `leave_ledger`; the migration role tries `UPDATE` | App role: permission denied (`42501`); migration role: refused by the append-only trigger |
| DB-9 | Ana applies twice, Mo approves one, Ana cancels the other | Balances are compared with the ledger | For every leave type, `entitlement`, `used` and `pending` equal the sums of the ledger deltas |
| DB-30 | Migrations at head | The catalog (`pg_constraint`, `pg_index`) is checked | Every foreign key column is the first column of at least one index |

### FR-14 Safe approvals (BR-10; Part C)

| ID | Given | When | Then |
|---|---|---|---|
| DB-10 *(concurrent)* | Ana has a pending 3-day annual request | Mo approves it twice at the same moment (two tabs) | Exactly one 200; the other 409 `INVALID_TRANSITION`; `used` increases by 3 once; exactly one `confirm` ledger row |
| DB-11 *(concurrent)* | Ana has 3 annual days available | Two 2-day annual requests (non-overlapping dates) are submitted at the same moment | Exactly one 201; the other 422 `INSUFFICIENT_BALANCE`; `pending` is 2, never 4 |
| DB-12 | Ana's pending request has `version` 1, then is changed (so it is now 2) | Mo approves with `If-Match: 1` | 409 `CONCURRENT_UPDATE`; status, balance and ledger unchanged |
| DB-13 | Two sessions load the same request; the first saves a change | The second saves its own change | `ConcurrentUpdateError` (SQLAlchemy `StaleDataError` underneath); the first change is kept |
| DB-14 | Connected as the app role | `SHOW statement_timeout`, `SHOW lock_timeout` | `5s` and `2s` |
| DB-15 | Another transaction holds a lock on Ana's balance for longer than 2 seconds | Ana submits a request | 503 `DATABASE_BUSY` with a `Retry-After` header; nothing saved |
| DB-16 | The concurrency test of DB-10 run with `LEAVEDESK_DEMO_NO_LOCKS=1` (test-only switch: a repository that ignores `lock=True` and writes rows back without a version check) | Mo approves twice at the same moment | The test fails and shows the bug: both approvals succeed. Without the switch it passes. This is the "fails without the lock" demonstration for the review |

### FR-15 Idempotent submit (BR-11; Part C)

| ID | Given | When | Then |
|---|---|---|---|
| DB-17 *(happy path)* | — | Ana submits the same body twice with `Idempotency-Key: k-1` | Both 201 with the same request `id`; the second has `Idempotent-Replayed: true`; one row; 3 days reserved, not 6 |
| DB-18 | Ana used `k-1` for 11–13 Nov | She sends `k-1` with 16–17 Nov | 422 `IDEMPOTENCY_KEY_REUSED`; nothing saved |
| DB-19 | Ana's submit with `k-2` failed with 409 (overlap) | The overlapping request is cancelled and she retries with `k-2` and the same body | 201 (the failed attempt stored nothing) |
| DB-20 | Ana used `k-1` | Mo submits his own request with `k-1` | 201; keys are scoped per employee |
| DB-21 *(concurrent)* | — | Ana sends the same body with `k-3` twice at the same moment | Both 201 with the same `id`; one row |

### FR-16 Notifications through the database (BR-12; Part C2)

| ID | Given | When | Then |
|---|---|---|---|
| DB-22 *(happy path)* | Ana has a pending request | Mo approves it | In the same transaction: the request is approved, one `approved` notification for Ana and one outbox row with status `pending` are stored |
| DB-23 | Ana has a pending request | An approval is forced to fail after its notifications are written (test raises before commit) | The transaction rolls back: request still pending, no new notification, no outbox row, no NOTIFY sent |
| DB-24 *(concurrent)* | 20 pending outbox rows | Two workers claim batches at the same moment | Every row is sent exactly once (no duplicates, none missed); all end with status `sent` |
| DB-25 | Mo has an open stream | A notification for Mo is committed | It arrives on Mo's stream within 1 second, through `LISTEN`, with no polling loop in the code |
| DB-26 | The email notifier fails | The worker processes the row | `attempts` becomes 1, `available_at` moves later, status stays `pending`; after the 5th failure, status is `failed` |

### FR-17 Login and database security (BR-13; Part D)

| ID | Given | When | Then |
|---|---|---|---|
| DB-27 | Ana's account | 5 wrong passwords, then the right one | All six get 401 `Invalid email or password`; `locked_until` is set; an `auth.lockout` audit row exists |
| DB-28 | Ana is locked | The lock period passes (clock moved in the test), then the right password | 200; `failed_login_count` is back to 0 |
| DB-29 | Connected as the app role | `CREATE TABLE x (id int)` | Permission denied (`42501`) |

### FR-18 Performance and pagination (Part B)

| ID | Given | When | Then |
|---|---|---|---|
| DB-31 | About 100,000 seeded requests, `ANALYZE` run | The manager's pending queue, an employee's history and the name search are explained before and after revision 0004 | Each "before" plan shows a sequential scan; each "after" plan uses the new index; both plans and timings are in `PERF.md` |
| DB-32 *(happy path)* | Ana has 45 requests | She walks `GET /leave-requests?limit=20` following `next_cursor` | Pages of 20, 20 and 5; every request exactly once, in order; the last page has `next_cursor: null` |
| DB-33 | Ana is on page 1 of a cursor walk | A new request with an earlier start date is added, then she fetches page 2 | No row is repeated or skipped from the original set (OFFSET would repeat one) |
| DB-34 | — | `cursor` and `offset=20` are both sent | 422 `VALIDATION_ERROR` |

---

## 13. Task breakdown (Capstone 3)

| Task | What | Implements | Files | Branch / PR |
|---|---|---|---|---|
| T14 | This spec update, API_SPEC v1.1, SCHEMA.md, AI notes | All of section 12 | `SPEC.md`, `API_SPEC.md`, `SCHEMA.md`, `AI_NOTES.md` | `docs/capstone3-spec` |
| T15 | Async repository: `LeaveRepository` methods become `async def`; `lock` keyword on `get_request` and `get_balance`; service awaits storage; tests updated | BR-10 groundwork | `leavedesk/domain/repository.py`, `service.py`, `inbox.py`, `leavedesk/api/`, `tests/` | `refactor/async-repository` |
| T16 | SQLAlchemy, psycopg, Alembic; database roles, timeouts and test database; settings | BR-10 timeouts, BR-13 roles, DB-14, DB-29 | `requirements.txt`, `docker-compose.yml`, `docker/postgres-init/`, `leavedesk/api/settings.py`, `.env.example` | `feature/db-infra` |
| T17 | Models and revision 0001 | BR-9, DB-3 to DB-6, DB-8, DB-30 | `leavedesk/db/`, `alembic.ini`, `migrations/` | `feature/db-infra` |
| T18 | `PostgresLeaveRepository`, database user store, error translation, session per request, test database reset | FR-12, DB-1, DB-2, DB-9 | `leavedesk/db/repository.py`, `leavedesk/db/users.py`, `leavedesk/api/`, `conftest.py` | `feature/pg-repository` |
| T19 | Locked approvals, version checks, `If-Match`, busy errors, concurrency tests | FR-14, DB-7, DB-10 to DB-16 | `leavedesk/domain/service.py`, `leavedesk/db/repository.py`, `leavedesk/api/`, `tests/db/` | `feature/safe-approvals` |
| T20 | Idempotency keys (revision 0002) | FR-15 | `leavedesk/db/`, `leavedesk/api/routes/leave.py`, `tests/db/` | `feature/safe-approvals` |
| T21 | Outbox (revision 0003), background drain, worker, `LISTEN` stream | FR-16 | `leavedesk/db/outbox.py`, `leavedesk/worker.py`, `leavedesk/api/stream.py`, `docker-compose.yml`, `tests/db/` | `feature/db-notifications` |
| T22 | Seed script, plans, query indexes (revision 0004), keyset pagination | FR-18 | `scripts/seed_perf.sql`, `PERF.md`, `migrations/`, `leavedesk/api/routes/leave.py` | `feature/perf` |
| T23 | Login lockout | FR-17 | `leavedesk/api/routes/auth.py`, `leavedesk/db/users.py`, `tests/` | `feature/login-lockout` |
| T24 | README, AI notes, review preparation | Definition of done | `README.md`, `AI_NOTES.md` | `docs/capstone3-wrapup` |

---

## 14. Definition of done (Capstone 3)
- The Day 2 API tests pass unchanged on PostgreSQL (DB-1), and the full suite still passes on the in-memory repository.
- The overlap (DB-6, DB-7), concurrency (DB-10, DB-11) and outbox rollback (DB-23) tests pass.
- `PERF.md` shows each indexed query switching from a sequential scan (DB-31).
- `docker compose up` runs the migrations, the API and the worker against PostgreSQL on a clean machine.
- `ruff check` and `ruff format --check` pass; no secrets in the repository; every query parameterised.

---

## 15. Change log
| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-10 | Initial specification for Capstone 1 |
| 1.1 | 2026-11-11 | T9: employees are registered through LeaveService, which creates their BR-1 balances. Service actions are async so notifications can be sent concurrently in T11. |
| 1.2 | 2026-11-12 | Capstone 2: repository gained `get_notification`, `save_notification` and `list_employees`; new `Inbox` (list unread first, mark read, mark all read). Leave rules unchanged. |
| 1.3 | 2026-11-16 | Capstone 3: scope 2.3–2.4; BR-8 audit rows; new BR-9 to BR-13; three new errors; section 12 (FR-12 to FR-18, DB-1 to DB-34); task breakdown and definition of done for Capstone 3. Database design moved to `SCHEMA.md`. Header version corrected (it still said 1.0). |
| 1.4 | 2026-11-16 | DB-16 names the demo switch `LEAVEDESK_DEMO_NO_LOCKS` and what the unsafe repository does. |
| 1.5 | 2026-11-17 | Capstone 4: the Angular web app is specified in `UI_SPEC.md` (v1.7). No leave rule changed. Building it checked the UI against this spec rather than a summary: three leave types (Annual, Sick, Casual), reason 10–500 characters after trimming, and a manager's pending list that includes their own requests (which BR-6 forbids them to approve). |
