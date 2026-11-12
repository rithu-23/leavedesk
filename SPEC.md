# LeaveDesk — Specification

**Version:** 1.0 (Capstone 1) · **Status:** Draft · **Author:** Rithu

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

---

## 5. Assumptions
- "Today" is given to LeaveService from outside rather than read from the computer clock, so the demo and tests give the same results on any day.
- Each employee has at most one manager.
- All requests fall within a single leave year.

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

| Error | Raised by | When | Planned HTTP status (Capstone 2) |
|---|---|---|---|
| `ValidationError` *(from Pydantic)* | Models | Input is badly formed (section 9.2) | 422 |
| `InvalidLeaveRequestError` | Policies, LeaveService | The request or action breaks a rule: no working days, policy rule (BR-3), half day on a weekend, rejection without a note | 422 |
| `InsufficientBalanceError` | LeaveService | `available` is less than the days requested (BR-4) | 422 |
| `OverlappingLeaveError` | LeaveService | The dates overlap a pending or approved request (BR-5) | 409 |
| `InvalidTransitionError` | LeaveService | The status change is not allowed (BR-6) | 409 |
| `NotAuthorisedError` | LeaveService | The person is not allowed to take this action (BR-6) | 403 |
| `NotFoundError` | Repository, LeaveService | An employee or request id does not exist | 404 |

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

## 12. Change log
| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-10 | Initial specification for Capstone 1 |
| 1.1 | 2026-11-11 | T9: employees are registered through LeaveService, which creates their BR-1 balances. Service actions are async so notifications can be sent concurrently in T11. |
| 1.2 | 2026-11-12 | Capstone 2: repository gained `get_notification`, `save_notification` and `list_employees`; new `Inbox` (list unread first, mark read, mark all read). Leave rules unchanged. |
