# LeaveDesk — API Specification (Capstone 2)

**Version:** 1.0 · **Builds on:** SPEC.md v1.1 (the leave rules are unchanged) · **Author:** Rithu

---

## 1. Scope

**In scope:** a REST API over the Capstone 1 domain package, with JWT login, role checks,
one error format, notification endpoints and a live notification stream.
Storage stays in memory behind `LeaveRepository`; three demo users are seeded at start-up.

**Out of scope (Capstone 3):** PostgreSQL storage, login lockout and rate limits, refresh tokens.

---

## 2. Conventions

| Topic | Rule |
|---|---|
| Format | JSON. Dates are `YYYY-MM-DD`; timestamps are UTC ISO 8601. |
| Day counts | Sent as strings (`"14.5"`), so decimal values are never rounded by a JSON float. |
| Authentication | `Authorization: Bearer <token>` on every route except `POST /auth/login`, `GET /health` and the docs pages. |
| Token | JWT signed with HS256. Claims: `sub` (employee id), `role`, `iat`, `exp`. Lifetime from `ACCESS_TOKEN_MINUTES` (default 30). Secret from `JWT_SECRET`, never in code. |
| Passwords | Stored only as Argon2id hashes; never stored or logged in plain text. |
| Request ID | Every response carries `X-Request-ID`. An incoming `X-Request-ID` is reused; otherwise a new one is created. |
| Pagination | `limit` 1–100 (default 20) and `offset` ≥ 0 (default 0). Lists return `{items, total, limit, offset}`. |
| Notifications | Sent after the response, using FastAPI `BackgroundTasks`. |

---

## 3. Endpoints

| Method | Path | Who may call it | Request | Success | Errors |
|---|---|---|---|---|---|
| POST | `/auth/login` | Anyone | Form fields `username` (email), `password` | 200 `Token` | 401, 422 |
| GET | `/health` | Anyone | — | 200 `{"status": "ok"}` | — |
| GET | `/employees/{id}/balance` | That employee, or their manager | — | 200 list of `Balance` | 401, 403, 404 |
| POST | `/leave-requests` | Any signed-in employee, for themselves | `LeaveRequestCreate` | 201 `LeaveRequestOut` | 400, 401, 409, 422 |
| GET | `/leave-requests` | Any signed-in employee (see visibility) | Query: `status`, `employee_id`, `sort` (`start_date` or `-start_date`), `limit`, `offset` | 200 page of `LeaveRequestOut` | 401, 403, 422 |
| GET | `/leave-requests/{id}` | The owner, or the owner's manager | — | 200 `LeaveRequestOut` | 401, 403, 404 |
| POST | `/leave-requests/{id}/approve` | The requester's manager | — | 200 `LeaveRequestOut` | 401, 403, 404, 409 |
| POST | `/leave-requests/{id}/reject` | The requester's manager | `{"reason": "..."}` | 200 `LeaveRequestOut` | 401, 403, 404, 409, 422 |
| DELETE | `/leave-requests/{id}` | The owner (cancels a pending request) | — | 200 `LeaveRequestOut` | 401, 403, 404, 409 |
| GET | `/notifications` | Self | Query: `unread`, `limit`, `offset` | 200 page of `NotificationOut`, unread first, then newest | 401, 422 |
| POST | `/notifications/{id}/read` | The recipient | — | 200 `NotificationOut` | 401, 404 |
| POST | `/notifications/read-all` | Self | — | 200 `{"updated": <count>}` | 401 |
| GET | `/notifications/stream` | Self | Token in the header **or** `?access_token=` | 200 `text/event-stream` | 401 |

**Visibility for `GET /leave-requests`:** employees see only their own requests; managers see their own
and their direct reports'. An `employee_id` filter outside that set returns 403.

**Why the stream also accepts `?access_token=`:** browsers' `EventSource` (used in Capstone 4) cannot send
custom headers. Tokens in URLs can end up in server logs, so the request-ID middleware logs the path
without the query string.

---

## 4. Schemas

| Schema | Fields |
|---|---|
| `Token` | `access_token`, `token_type` (`"bearer"`), `expires_in` (seconds) |
| `LeaveRequestCreate` | `leave_type`, `start_date`, `end_date`, `reason`, `half_day` (default `false`) |
| `RejectBody` | `reason` (1–500 characters after trimming) |
| `LeaveRequestOut` | `id`, `employee_id`, `leave_type`, `start_date`, `end_date`, `half_day`, `reason`, `status`, `days`, `created_at`, `decided_by`, `decision_note` |
| `Balance` | `leave_type`, `entitlement`, `used`, `pending`, `available` |
| `NotificationOut` | `id`, `event`, `message`, `read`, `created_at` |
| `Page[T]` | `items` (list of T), `total`, `limit`, `offset` |

`employee_id` is never accepted in `LeaveRequestCreate`; it always comes from the token.

---

## 5. Error contract

Every error, whatever its status, has this shape:

```json
{
  "error": {
    "code": "OVERLAPPING_LEAVE",
    "message": "Dates overlap existing request LR-3f9a1c2b.",
    "request_id": "6c1d0f2e9b7a4c55",
    "details": null
  }
}
```

| Status | `code` | When | Source |
|---|---|---|---|
| 400 | `BAD_REQUEST` | The request body is not valid JSON | Request parsing |
| 401 | `UNAUTHENTICATED` | Token missing, invalid or expired; wrong email or password | Security |
| 403 | `FORBIDDEN` | Signed in but not allowed (wrong role or not the owner or manager) | `NotAuthorisedError`, role checks |
| 404 | `NOT_FOUND` | The employee, request or notification does not exist, or the notification belongs to someone else | `NotFoundError` |
| 409 | `OVERLAPPING_LEAVE` | Dates overlap a pending or approved request | `OverlappingLeaveError` |
| 409 | `INVALID_TRANSITION` | The request is not pending | `InvalidTransitionError` |
| 422 | `VALIDATION_ERROR` | Input fails a schema rule; `details` lists each `{field, message}` | Pydantic |
| 422 | `INVALID_LEAVE_REQUEST` | A leave rule is broken (policy, no working days, missing reason) | `InvalidLeaveRequestError` |
| 422 | `INSUFFICIENT_BALANCE` | Not enough days available | `InsufficientBalanceError` |
| 500 | `INTERNAL_ERROR` | Anything unexpected; generic message, no internal details | Fallback handler |

**Login errors are generic:** a wrong password and an unknown email both return 401 with the message
`Invalid email or password`, so the API never reveals which emails exist.

---

## 6. Notifications through the API

1. Submit, approve, reject and cancel save the change and store the notifications.
2. The API sends its response.
3. A background task then sends each notification through the email stub and the in-app channel.
4. In-app delivery publishes to the recipient's open stream(s). Each event looks like:
   `event: notification` and `data: <NotificationOut as JSON>`. A keep-alive comment is sent every 15 seconds.

---

## 7. Acceptance criteria

The cast and "today" match SPEC.md section 6 (Ana reports to Mo; Lee manages nobody Ana knows).

| ID | Given | When | Then |
|---|---|---|---|
| API-1 | Ana's correct email and password | `POST /auth/login` | 200 with a bearer token |
| API-2 | Ana's email with a wrong password | `POST /auth/login` | 401 `UNAUTHENTICATED`, message `Invalid email or password` |
| API-3 | An email that does not exist | `POST /auth/login` | Exactly the same 401 and message as API-2 |
| API-4 | No token | Any protected endpoint | 401 `UNAUTHENTICATED` |
| API-5 | An expired or tampered token | Any protected endpoint | 401 `UNAUTHENTICATED` |
| API-6 | Ana signed in, 18 annual days | `POST /leave-requests` annual 11–13 Nov | 201, `status` `pending`, `days` `"3"`; a background notification task is queued |
| API-7 | Ana has a pending request 11–13 Nov | She requests sick leave on 13 Nov | 409 `OVERLAPPING_LEAVE` |
| API-8 | — | Ana requests end date 11 Nov before start 13 Nov | 422 `VALIDATION_ERROR` mentioning `end_date` |
| API-9 | Ana has 18 annual days | She requests 16 Nov – 11 Dec (20 days) | 422 `INSUFFICIENT_BALANCE` |
| API-10 | — | `POST /leave-requests` with a body that is not JSON | 400 `BAD_REQUEST` |
| API-11 | Ana and Mo both have requests | Ana calls `GET /leave-requests` | Only Ana's requests; `status` filter and `total` work |
| API-12 | Ana signed in | `GET /leave-requests?employee_id=E-MO` | 403 `FORBIDDEN` |
| API-13 | Ana has a pending request | Mo calls `GET /leave-requests?status=pending` | Ana's request is in the list |
| API-14 | — | `GET /leave-requests/LR-NOPE` | 404 `NOT_FOUND` |
| API-15 | Ana has a request | Lee calls `GET /leave-requests/{id}` | 403 `FORBIDDEN` |
| API-16 | Ana has a pending 3-day request | Mo approves it | 200 `approved`; Ana's annual balance shows `used` `"3"` |
| API-17 | Ana has a pending request | Ana tries to approve it | 403 `FORBIDDEN` |
| API-18 | Ana's request is approved | Mo approves it again | 409 `INVALID_TRANSITION` |
| API-19 | Ana has a pending request | Mo rejects with no `reason`, then with a reason | First 422 `VALIDATION_ERROR`; then 200 `rejected` |
| API-20 | Ana has a pending request | Mo cancels it; Ana cancels it; Ana cancels it again | 403, then 200 `cancelled`, then 409 |
| API-21 | — | Balance of Ana requested by Ana, by Mo, by Lee, and an unknown id by Mo | 200 (3 leave types), 200, 403, 404 |
| API-22 | Ana has applied | Mo calls `GET /notifications` and `?unread=true` | 1 unread `submitted` notification in both |
| API-23 | Mo has a notification | Mo marks it read; Ana tries to mark it read | 200 with `read` `true`; 404 for Ana |
| API-24 | Mo has unread notifications | `POST /notifications/read-all` | `updated` equals the unread count; then `?unread=true` is empty |
| API-25 | Mo has an open stream | A notification is delivered in-app to Mo | It arrives on Mo's stream, not on Ana's |
| API-26 | No token | `GET /notifications/stream` | 401 `UNAUTHENTICATED` |
| API-27 | — | Any request, with and without an `X-Request-ID` header | The response has `X-Request-ID`; an incoming value is reused |
| API-28 | The seeded users | Their stored passwords are inspected | Each is an Argon2id hash (`$argon2id$…`), never the plain password |

---

## 8. Implementation plan

| Task | What | Files | PR |
|---|---|---|---|
| A1 | This specification | `API_SPEC.md` | #9 |
| A2 | Settings from environment variables | `leavedesk/api/settings.py` | #10 |
| A3 | Argon2id hashing and JWT create/verify | `leavedesk/api/security.py` | #10 |
| A4 | Seeded users and app wiring | `leavedesk/api/users.py`, `leavedesk/api/main.py` | #10 |
| A5 | Error contract and exception handlers | `leavedesk/api/errors.py` | #10 |
| A6 | Request-ID and logging middleware | `leavedesk/api/middleware.py` | #10 |
| A7 | Auth and role dependencies | `leavedesk/api/deps.py` | #10 |
| A8 | Auth, balance and leave routes | `leavedesk/api/routes/` | #10 |
| A9 | Notification routes, background sending, SSE stream | `leavedesk/api/routes/notifications.py`, `leavedesk/api/stream.py` | #10 |
| A10 | API tests for API-1 to API-28 (notifier mocked) | `tests/api/` | #10 |
| A11 | Ruff lint and format | `pyproject.toml` | #10 |
| A12 | Dockerfile, Docker Compose (`api` + `db`), `.env.example` | project root | #11 |
| A13 | AI usage log | `AI_NOTES.md` | #10, #11 |

---

## 9. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-12 | Initial API specification for Capstone 2 |
