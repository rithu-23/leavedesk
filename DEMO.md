# LeaveDesk — Final demo script (Capstone 4, about 10 minutes)

Follows the workshop's final-demo order. Times are targets; rehearse once with a timer.

## Before the demo (5 minutes earlier)

| ✓ | Check | Command / action |
|---|---|---|
| ☐ | Fresh demo data, whole stack running | `docker compose down -v && docker compose up -d --build --wait` |
| ☐ | Every service healthy | `docker compose ps` (db, api, worker, web healthy; migrate exited) |
| ☐ | Two browser windows | Normal window: http://localhost:8080 signed in as **Ana**. Incognito window: signed in as **Mo**. Side by side. |
| ☐ | Terminal ready in `frontend/` | for `npm run e2e` |
| ☐ | Open in editor tabs | `UI_SPEC.md` (change log), `SPEC.md` §15, `PERF.md` §2, `AI_NOTES.md` Entry 22 |
| ☐ | Password at hand | `grep '^DEMO_PASSWORD=' .env` |

## 1. The four specs and how they changed (2 min)

- **SPEC.md** (Day 1, v1.0 → v1.5): leave rules and Given/When/Then criteria. Show §15, the change log: each version says what changed and why.
- **API_SPEC.md** (Day 2, v1.1): endpoints, one error shape, and the Day 3 additions (`If-Match`, `Idempotency-Key`, keyset cursor).
- **SCHEMA.md** (Day 3): why identity keys, numeric(5,1), the EXCLUDE constraint and each index.
- **UI_SPEC.md** (Day 4, v1.0 → v1.7): show the change log. *"The spec changed seven times while I built it, and every change says what found it: two came from my own manual testing (Casual labelled as Sick, no lockout hint), two from reading the backend code, one from the accessibility audit, one from the end-to-end test."*

## 2. Live employee-to-manager flow (3 min)

1. **Ana:** My leave. Point at the balance card (*"a `computed()` signal over the store"*) and the table (status filter, pagination).
2. **Ana:** Apply. Show a validation error (end before start), then submit a valid request with a reason of at least 10 characters. It appears as **Pending**, and Annual *available* drops.
3. **Mo's window:** the bell count goes up within a second (*"Server-Sent Events, not polling"*). Open **Approvals** (*"lazy-loaded, and the role guard uses `canMatch`, so employees never download this code"*).
4. **Mo:** Approve → confirm dialog. The row disappears instantly (*"optimistic update with `If-Match`; if the API says 409 it goes back"*).
5. **Ana's window, no refresh:** the toast "…was approved", the bell count, Annual *used* goes up, the row turns **Approved**. Click the bell: the panel lists it and the count goes to 0.
6. Optional, 20 seconds: narrow the window to phone width. The menu collapses and nothing scrolls sideways.

## 3. One PostgreSQL finding and a live notification (2 min)

Pick **one**:

- **Index proof (PERF.md §2), Q1 manager's pending queue:** before, a *Seq Scan* removing 90,000 rows, 2,242 buffers, 11.9 ms; after, an *Index Scan* on the partial index `ix_leave_requests_pending`, 403 buffers, 0.53 ms. *"Partial index: only pending rows are in it, so it stays small."*
- **Or keyset vs OFFSET (P1/P2):** OFFSET 50000 read 50,020 rows to return 20 (22.7 ms); keyset read 20 rows (0.03 ms).
- **Or the concurrency test:** `LEAVEDESK_DEMO_NO_LOCKS=1 python -m pytest tests/db/test_concurrency.py -k db10` fails (two approvals overspend the balance); without the switch it passes (row lock plus version column).

The live notification was already shown in part 2. Trace it in one sentence: *"approve writes an outbox row in the same transaction → the SKIP LOCKED worker sends it → pg_notify wakes the API's LISTEN → the SSE stream → the Angular store's EventSource → the bell's computed count."*

## 4. One mistake the AI made that I caught (1 min)

**AI_NOTES.md Entry 22:** the generated code labelled **Casual leave as "Sick"**. It trusted a handoff summary listing two leave types and wrote "Annual if ANNUAL, otherwise Sick". *"I caught it by comparing the balance card with pgAdmin. The fix is one typed label map, `Record<LeaveType, string>`, so a leave type without a label won't compile, plus tests with the real data, and the spec corrected to v1.2."*

Backup example: Entry 27, the end-to-end test found the role guard sending signed-out managers back to the wrong page.

## 5. Reviewer questions (2 min): short answers

| Likely question | Answer |
|---|---|
| Why signals and not only RxJS? | Signals hold state you read now (`unreadCount()`, `loading()`), with automatic, fine-grained updates and no subscriptions to clean up. RxJS stays where there is a stream over time: HttpClient and the SSE connection. Their results are written into signals. |
| Why a hand-written store and not NgRx? | Two small features and one developer; a service with private signals, read-only views and `computed()` gives loading/error/success without the boilerplate. NgRx SignalStore is the next step if the state grows (it's the stretch goal). |
| What does the interceptor do? | Adds `Authorization: Bearer` to `/api/` calls only (never other sites, never the login call) and signs the user out on a 401. |
| Guards are client-side; isn't that insecure? | Guards only shape the experience. The API checks the token and the role on every request; an employee calling approve directly gets 403. |
| Where is the token stored, and why? | A signal, mirrored to `sessionStorage`: it survives a refresh and is gone when the tab closes. Like any storage JavaScript can read, it's exposed by an XSS bug; Angular escapes templates and we never bind user data as HTML. |
| How do you avoid CORS? | The browser only ever talks to one address. `/api` is forwarded to FastAPI by the dev server (`proxy.conf.json`) and by nginx in Docker, so there's no cross-origin request and no CORS configuration to get wrong. |
| EventSource can't send headers; how is the stream authenticated? | `?access_token=` on that one endpoint. Risk: URLs end up in logs, so nginx doesn't log that location, and the token expires in 30 minutes. |
| What is an optimistic update and when does it roll back? | The row disappears before the API answers; on any error it goes back to the same position, and on 409 the list reloads, because someone else changed it. |
| How do you know it's accessible? | ESLint template accessibility rules, plus axe-core (WCAG 2.1 A/AA) in Playwright at 1280 and 375 px with zero violations, plus a keyboard-only walk-through. axe found a real critical issue: the notification panel was announced as a menu. |
| What do the tests cover? | 61 unit tests (stores, forms, guards, interceptor, SSE wrapper, dialogs, failure paths like 401, 409, 422 and 503) with HTTP mocked, and Playwright against docker compose for the full flow and accessibility. |
