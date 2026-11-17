# LeaveDesk — UI Specification (Capstone 4)

**Version:** 1.2 · **Status:** approved for build · **Builds on:** SPEC.md v1.4, API_SPEC.md v1.1, SCHEMA.md v1.4

This document describes the Angular web app that sits on top of the LeaveDesk API: its screens, what each screen shows in every state, and the acceptance criteria (Given/When/Then) that the tests check. It is written before any frontend code, in line with Spec-Driven Development.

---

## 1. Scope

**In scope**

- Login and logout for employees and managers.
- My leave: the user's own requests (table with status filter and pagination) and leave balance.
- Apply for leave, including half-day leave and server-side errors shown inline.
- Cancel a pending request (owner only).
- Manager approvals: approve or reject pending requests from direct reports.
- Notifications: toolbar bell with unread count, live updates, toast pop-ups and a panel.
- Phone (375 px) and desktop layouts; keyboard and screen-reader access.
- Unit tests (Vitest + Angular Testing Library) and one end-to-end test (Playwright).
- Running the app in Docker Compose next to the API, worker and database.

**Out of scope (v1.0)**

- Refresh tokens: the API issues 30-minute access tokens only, so the user signs in again after expiry.
- PWA, service worker and Web Push (stretch goal).
- NgRx SignalStore (stretch goal; v1.0 uses hand-written signal stores).
- Cursor (keyset) pagination in the UI: the UI uses `limit`/`offset`, which the API still supports.
- Editing a request after submission, admin screens, multiple tenants in one browser.

## 2. Technology

| Area | Choice | Why |
|---|---|---|
| Framework | Angular 22, standalone components, no NgModules | Current Angular default; each component declares its own imports, so features are self-contained. |
| Templates | Built-in control flow (`@if`, `@for`, `@switch`) | Current syntax; clearer than `*ngIf`/`*ngFor`. |
| State | Signals (`signal`, `computed`, `effect`) in feature stores | Synchronous, fine-grained UI state with no manual subscriptions. |
| Async edges | RxJS for `HttpClient` calls and the SSE stream | Streams of events over time are what RxJS is for; results are written into signals. |
| UI kit | Angular Material + CDK | Accessible table, paginator, form fields, dialog, snackbar, badge and menu out of the box. |
| Forms | Reactive Forms | Validation rules live in TypeScript and are unit-testable. |
| Unit tests | Vitest + Angular Testing Library, HTTP mocked with `provideHttpClientTesting` | Angular 22 default runner; tests interact with the screen the way a user does. |
| E2E | Playwright | Drives a real browser against the full Docker stack. |
| Quality | ESLint (angular-eslint) + Prettier | Lint and formatting checked in CI-style commands. |

## 3. How the app reaches the API

A browser only lets a web page call servers at the **same address** (scheme, host and port) unless the server opts in. The Angular app and the API run on different ports, so instead of changing the API, the app and the API are served under **one address**, and every API call goes to a path starting with `/api/`:

| Where | App served at | `/api/*` forwarded to | How |
|---|---|---|---|
| Development (`npm start`) | `http://localhost:4200` | `http://localhost:8000` (prefix `/api` removed) | `frontend/proxy.conf.json` |
| Docker Compose | `http://localhost:8080` | `http://api:8000` (prefix `/api` removed) | `frontend/nginx.conf` in the `web` service |

Consequences:

- The Angular code always calls relative URLs such as `/api/leave-requests`. No environment-specific base URL.
- The API needs no CORS middleware; the backend and its 175 tests are unchanged.
- nginx disables response buffering on `/api/notifications/stream` so Server-Sent Events arrive immediately.

## 4. Users and roles

The app reads the user's identity from the JWT returned by `POST /auth/login` (there is no `/me` endpoint): `sub` = employee id, `role` = `employee` or `manager`, `exp` = expiry (Unix seconds).

| Demo user | Employee id | Role | Notes |
|---|---|---|---|
| ana@leavedesk.test | E-ANA | employee | Reports to E-MO |
| mo@leavedesk.test | E-MO | manager | Approves Ana's requests |
| lee@leavedesk.test | E-LEE | manager | Has no reports in the demo data |

All demo users use `DEMO_PASSWORD` from `.env`.

| Capability | Employee | Manager |
|---|---|---|
| Log in / out, bell and notifications | ✓ | ✓ |
| My leave, apply, cancel own pending request | ✓ | ✓ |
| Approvals screen | ✗ (link hidden, route blocked) | ✓ |

## 5. Screens and routes

| Route | Screen | Access | Loading |
|---|---|---|---|
| `/login` | Login | Signed-out users only (signed-in users are sent to `/leave`) | Eager |
| `/leave` | My leave (balance card + requests table) | Signed in | Eager |
| `/leave/apply` | Apply for leave | Signed in | Eager |
| `/approvals` | Manager approvals | Signed in **and** `role = manager` | **Lazy** (separate bundle) |
| `''` | Redirects to `/leave` | — | — |
| `**` | Redirects to `/leave` | — | — |

**App shell (every signed-in screen):** a Material toolbar with the LeaveDesk name, navigation links (My leave, Apply, Approvals for managers only), the notification bell and a Log out button. Below 600 px the navigation links collapse into a menu button.

### 5.1 Login

- Fields: Email (required, email format) and Password (required).
- Submit is disabled while the form is invalid or a request is in flight; the button shows a spinner while waiting.
- Request: `POST /api/auth/login` as `application/x-www-form-urlencoded` with `username` and `password`.
- Success: the token is stored, the SSE stream opens, and the user goes to `returnUrl` if present, otherwise `/leave`.
- Any 401 (wrong password, unknown email or locked account) shows one generic message: **"Invalid email or password."** The UI never says which part was wrong or that an account is locked.
- After 3 failed attempts in a row on the page, a fixed hint appears: **"After 5 failed attempts, sign-in is paused for 15 minutes."** It is shown whatever email was typed, so it reveals nothing about any account.

### 5.2 My leave

- **Balance card:** one row per leave type, in the order Annual, Sick, Casual, showing entitlement, used, pending and available, from `GET /api/employees/{sub}/balance`. Decimal strings from the API are converted to numbers once, in the API service. Derived values (for example the total available days and the "low balance" flag when available < 2) are `computed()` signals over the balance signal.
- **Requests table:** `GET /api/leave-requests?employee_id={sub}&status={filter}&sort=-start_date&limit={size}&offset={offset}`.
  - Columns: Dates (start–end, "½ day" tag when `half_day`), Type, Days, Status (coloured chip), Reason, Actions.
  - Status filter: All, Pending, Approved, Rejected, Cancelled. Changing the filter returns to page 1.
  - Paginator: page sizes 5, 10, 20 (default 10), total from the response.
  - Actions: **Cancel** on pending rows only → confirm dialog → `DELETE /api/leave-requests/{id}`.
  - Below 600 px the Reason column is hidden and the table scrolls horizontally if needed.
- Button **Apply for leave** links to `/leave/apply`.

### 5.3 Apply for leave

| Field | Control | Rules |
|---|---|---|
| Leave type | Select: Annual, Sick, Casual | Required |
| Start date | Datepicker (MM/DD/YYYY) | Required |
| End date | Datepicker (MM/DD/YYYY) | Required; must be on or after the start date |
| Half day | Checkbox | Allowed only when start and end are the same day |
| Reason | Textarea | Required, not only spaces, at most 500 characters |

- Cross-field errors (end before start, half day on a multi-day range) appear under the End date / Half day fields as soon as both values are present.
- Dates are sent as `YYYY-MM-DD` in local time (no time-zone shift).
- Each submission sends a new `Idempotency-Key` header (`crypto.randomUUID()`), generated when the user presses Submit, so a double-click or retry of the same press cannot create two requests.
- Success (201): snackbar "Leave request submitted", the leave store and balance reload, and the user returns to `/leave`.
- Server errors are shown **inline, above the Submit button**, using the API's `error.message`:
  - 409 `OVERLAPPING_LEAVE` → the overlap message.
  - 409 `INSUFFICIENT_BALANCE` → the balance message.
  - 422 validation → the message, plus field-level messages from `error.details` where a field can be matched.
- The form keeps the user's input after an error.

### 5.4 Manager approvals (lazy-loaded)

- List: `GET /api/leave-requests?status=pending&sort=start_date&limit={size}&offset={offset}` (the API returns only the manager's reports).
- Each row: employee id, dates, type, days, reason, **Approve** and **Reject** buttons.
- **Approve:** confirm dialog ("Approve 3 days of annual leave for E-ANA?") → on confirm the row is removed from the list **immediately** (optimistic update) → `POST /api/leave-requests/{id}/approve` with header `If-Match: {version}`.
- **Reject:** dialog with a required Reason field → same optimistic removal → `POST /api/leave-requests/{id}/reject` with body `{reason}` and `If-Match: {version}`.
- **On any error the row is put back where it was** and a snackbar shows the message. On 409 (request changed by someone else, or no longer pending), the list also reloads from the server.

### 5.5 Notifications

- **Bell** (toolbar): a Material badge shows the unread count (hidden when 0). The count is a `computed()` signal over the notification store's list.
- **On sign-in** the store loads `GET /api/notifications?limit=20` and opens `EventSource('/api/notifications/stream?access_token={jwt}')`. (EventSource cannot send headers, so the token goes in the query string; see §9.)
- **On each `notification` event** the new item is added to the top of the list and a snackbar shows its message for 5 seconds with a **View** action that opens the panel. If the event is about a decision (`approved`, `rejected`, `cancelled`), the leave store and balance also reload, so the employee's screen updates without a refresh.
- **Opening the panel** shows the 20 most recent notifications (newest first, unread in bold) and calls `POST /api/notifications/read-all` if anything is unread; items then show as read.
- **On sign-out or token expiry** the stream is closed and the store is cleared.

## 6. States on every list

| Screen | Loading | Empty | Error |
|---|---|---|---|
| Balance card | Progress bar in the card | "No balance found" | Message + **Retry** |
| My leave table | Progress bar above the table | "No leave requests yet" (or "No {status} requests" when filtered) | Message + **Retry** |
| Approvals | Progress bar | "Nothing waiting for approval" | Message + **Retry** |
| Notifications panel | Spinner | "No notifications" | "Couldn't load notifications" + **Retry** |

Each feature store exposes `loading`, `error` and `data` signals; screens render only from those signals.

## 7. Error handling (all screens)

The API returns `{"error": {"code", "message", "request_id", "details"}}`. One helper turns any HTTP error into `{status, code, message, requestId}`.

| HTTP | Behaviour |
|---|---|
| 401 on any call except login | Sign out, close the stream, go to `/login?returnUrl=…`, snackbar "Your session has ended. Please sign in again." |
| 403 | Snackbar "You don't have permission to do that." |
| 404 | Inline "Not found" in the screen that asked. |
| 409 / 422 | Inline on the form or snackbar on list actions, using `error.message`. |
| 503 `DATABASE_BUSY` | Snackbar "The server is busy. Please try again." |
| Network error (status 0) | Snackbar "Can't reach the server." |

The `request_id` is logged to the browser console for debugging, never shown as the main message.

## 8. Accessibility and responsive layout

- Every form control has a visible `<mat-label>`; error messages are linked to their fields by Material (`aria-describedby`).
- Everything works with the keyboard: Tab order follows the visual order, dialogs trap focus and close on Escape, focus returns to the button that opened them.
- The bell is a `<button>` with `aria-label="Notifications, {n} unread"`. A visually hidden `aria-live="polite"` region announces "{n} unread notifications" when the count changes.
- Status chips use text, not colour alone.
- Layouts are mobile-first with CSS Grid/Flexbox. At **375 px** wide: no horizontal page scroll, toolbar links collapse into a menu, forms are single-column, dialogs are full width.

## 9. Security decisions

| Topic | Decision | Trade-off |
|---|---|---|
| Token storage | Signal in `AuthService`, mirrored to `sessionStorage` (key `leavedesk.token`) | Survives a page refresh, cleared when the tab closes. Like any storage readable by JavaScript, it is exposed if the page has an XSS bug; Angular's template escaping and no `innerHTML` with user data reduce that risk. |
| Expiry | On load and on each check, an expired token is discarded; a timer signs the user out at `exp` | No refresh tokens in the API, so the session simply ends. |
| Token in SSE URL | `?access_token=` because EventSource cannot send headers | The token may appear in server/proxy access logs; acceptable for the workshop, and it expires in 30 minutes. |
| Route guards | `authGuard` and `roleGuard('manager')` | Guards only improve the experience; the API still enforces every rule (it returns 401/403 regardless of the UI). |
| Secrets | No secrets in the frontend; `DEMO_PASSWORD` is only typed into the login form or read from the environment by the E2E test | — |

## 10. Acceptance criteria

IDs are referenced by the tests (`UI-n`).

### Authentication

- **UI-1 Login form validation.** Given the login page, when the email is empty or not an email, or the password is empty, then the field shows an error and Submit is disabled.
- **UI-2 Successful login.** Given Ana's correct credentials, when she submits, then the token is stored, the toolbar shows her navigation without an Approvals link, and she lands on `/leave`.
- **UI-3 Generic login error.** Given a wrong password (or a locked account), when the user submits, then "Invalid email or password." is shown and the user stays on `/login`. After 3 failures in a row, the fixed lockout hint is also shown.
- **UI-4 Token on requests.** Given a signed-in user, when the app calls any `/api/` endpoint other than `/api/auth/login`, then the request carries `Authorization: Bearer {token}`.
- **UI-5 Session end.** Given a signed-in user, when any API call (other than login) returns 401, then the user is signed out, the stream is closed, and the app shows `/login` with a `returnUrl`.
- **UI-6 Guards.** Given a signed-out user, when they open `/leave`, then they are sent to `/login`. Given Ana (employee), when she opens `/approvals`, then she is sent to `/leave` and the approvals bundle is not loaded.
- **UI-7 Logout.** Given a signed-in user, when they press Log out, then the token is removed, the stream is closed, stores are cleared and `/login` is shown.

### My leave

- **UI-8 Balance card.** Given Ana is signed in, when `/leave` loads, then the balance card shows entitlement, used, pending and available for each leave type, as numbers.
- **UI-9 Requests table.** Given Ana has requests, when `/leave` loads, then they appear newest first with 10 per page and the paginator shows the total.
- **UI-10 Status filter.** Given the table, when Ana picks "Pending", then the list reloads with `status=pending` from page 1.
- **UI-11 Cancel.** Given a pending request, when Ana confirms Cancel, then `DELETE` is sent, the row shows Cancelled, and the balance reloads. Approved, rejected and cancelled rows have no Cancel button.

### Apply for leave

- **UI-12 Date range validation.** Given the apply form, when the end date is before the start date, then "End date must be on or after the start date" is shown and Submit is disabled.
- **UI-13 Half-day rule.** Given a multi-day range, when Half day is ticked, then "Half day is only allowed for a single day" is shown and Submit is disabled.
- **UI-14 Submit.** Given a valid form, when Ana submits, then `POST /api/leave-requests` is sent with an `Idempotency-Key` header, a success snackbar appears, and she returns to `/leave` where the new request is pending and `available` has dropped by its days.
- **UI-15 Overlap error inline.** Given Ana already has leave on those dates, when she submits, then the API's 409 `OVERLAPPING_LEAVE` message appears above the Submit button and her input is kept.
- **UI-16 Insufficient balance inline.** Given the request needs more days than available, when Ana submits, then the 409 `INSUFFICIENT_BALANCE` message appears inline.

### Approvals

- **UI-17 Pending queue.** Given Mo is signed in, when he opens `/approvals`, then the lazily loaded screen lists his reports' pending requests, oldest start date first.
- **UI-18 Approve with confirm.** Given a pending request, when Mo presses Approve, then a confirm dialog opens; when he confirms, the row disappears immediately and `POST …/approve` is sent with `If-Match: {version}`.
- **UI-19 Reject needs a reason.** Given the reject dialog, when the reason is empty, then Reject is disabled; with a reason, the row disappears and `POST …/reject` is sent with `{reason}`.
- **UI-20 Rollback on error.** Given an optimistic approve or reject, when the API returns an error, then the row is restored at its original position and the error message is shown; on 409 the list reloads.

### Notifications

- **UI-21 Unread count.** Given the notification store holds 3 unread and 2 read items, then the bell badge shows 3 and its accessible name is "Notifications, 3 unread"; with 0 unread the badge is hidden.
- **UI-22 Live notification.** Given Ana is signed in, when Mo approves her request, then within a few seconds a snackbar shows the approval message, the badge count goes up, and her balance and table reload without a page refresh.
- **UI-23 Mark read.** Given unread notifications, when the panel opens, then `POST /api/notifications/read-all` is sent and the badge goes to 0.
- **UI-24 Panel states.** Given the panel, then it shows a spinner while loading, "No notifications" when the list is empty, and an error with Retry when loading fails.
- **UI-25 Stream lifecycle.** Given a user signs in, then exactly one SSE connection opens; when they sign out or the session ends, it closes.

### Layout and accessibility

- **UI-26 Phone width.** Given a 375 px wide viewport, when any screen is shown, then there is no horizontal page scroll and all actions are reachable.
- **UI-27 Keyboard.** Given keyboard-only use, then the user can sign in, apply, approve (including the dialog) and open the notification panel without a mouse.

### Running the whole system

- **UI-28 Docker.** Given `docker compose up -d --build`, then `http://localhost:8080` serves the app, `/api/health` returns `{"status":"ok"}` through nginx, and the live notification stream works through nginx.

## 11. Test plan

**Unit tests (Vitest + Angular Testing Library, HTTP mocked) — at least 6:**

| # | Test | Criteria |
|---|---|---|
| 1 | Login form: invalid input disables Submit; 401 shows the generic message; hint after 3 failures | UI-1, UI-3 |
| 2 | Auth interceptor adds the Bearer header and signs out on 401 | UI-4, UI-5 |
| 3 | `roleGuard('manager')` allows managers and redirects employees | UI-6 |
| 4 | Date-range and half-day validators | UI-12, UI-13 |
| 5 | Apply form shows the 409 overlap message inline | UI-15 |
| 6 | Leave store: loading → success, loading → error states | UI-8, UI-9 |
| 7 | Approvals: optimistic removal and rollback on error | UI-18, UI-20 |
| 8 | Notification store `unreadCount` and the bell's badge and accessible name | UI-21 |

**End-to-end test (Playwright), against `docker compose up` on `http://localhost:8080`:**

1. Reset to fresh demo data first (`docker compose down -v && docker compose up -d --build`), because every approved run uses up Ana's balance.
2. Ana signs in and notes her ANNUAL `used` and `available` values.
3. Ana applies for a single working day of annual leave in a future week; `available` drops by 1 (UI-14).
4. In a second browser context, Mo signs in, opens Approvals and approves Ana's request (UI-17, UI-18).
5. Back in Ana's context, without reloading: a snackbar shows the approval, the bell count rises (UI-22), and ANNUAL `used` has increased by 1.

**Done when:** this Playwright test passes against the Docker Compose stack (database, migrate, API, worker and web).

## 12. Frontend structure

```
frontend/
├── proxy.conf.json          dev: /api → localhost:8000
├── nginx.conf               Docker: serve app, /api → api:8000
├── Dockerfile               build with Node, serve with nginx
├── e2e/                     Playwright test
└── src/app/
    ├── core/                auth service, interceptor, guards, error helper, API types
    ├── shared/              confirm dialog, status chip, state views (loading/empty/error)
    ├── layout/              app shell: toolbar, navigation, bell
    └── features/
        ├── auth/            login page
        ├── leave/           leave API service, leave store, my-leave page, apply page
        ├── approvals/       approvals routes (lazy), page, reject dialog
        └── notifications/   notification API service, store, SSE wrapper, panel
```

Rules: features may import from `core/` and `shared/`, never from each other (the leave and notifications stores talk only through `core/` events or the shell). Components contain presentation; API calls live in services; state lives in stores.

## 13. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-17 | First UI spec for Capstone 4. Backend references corrected to PostgreSQL 17 (the Capstone 4 handoff said 16). |
| 1.1 | 2026-11-17 | §5.1 and UI-3: fixed lockout hint after 3 failed sign-ins (found during manual testing: users got no hint about the 15-minute lock). §5.3: date format MM/DD/YYYY and a 500-character reason limit made explicit. |
| 1.2 | 2026-11-17 | Leave types are ANNUAL, SICK and **CASUAL** (the Capstone 4 handoff listed only two; CASUAL exists since Capstone 1 and in the database). All labels come from one typed map; unknown codes are shown as-is. Found during manual testing: CASUAL rows were labelled "Sick". |
