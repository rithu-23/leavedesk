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