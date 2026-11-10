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