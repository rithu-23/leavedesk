# LeaveDesk web app

The Angular front end of LeaveDesk (Capstone 4). The full setup, Docker instructions and the
command table are in the repository's main [README](../README.md); the screens and acceptance
criteria are in [UI_SPEC.md](../UI_SPEC.md).

## Stack

Angular 22 (standalone components, zoneless, signals, built-in control flow), Angular Material and
CDK, Reactive Forms, RxJS at the edges (HttpClient, Server-Sent Events), Vitest with Angular Testing
Library, Playwright with axe-core, ESLint and Prettier.

## Everyday commands

```bash
npm install
npm start            # http://localhost:4200, API expected on http://localhost:8000
npm test             # unit tests
npm run lint
npm run format:check
npm run e2e          # end-to-end tests; needs docker compose up -d --build --wait
```

## Structure

| Folder                            | What it holds                                                   |
| --------------------------------- | --------------------------------------------------------------- |
| `src/app/core/`                   | API types, error helper, `AuthService`, JWT interceptor, guards |
| `src/app/layout/`                 | The toolbar shell (navigation, bell, log out)                   |
| `src/app/shared/`                 | Confirm dialog, status chip, leave-type labels                  |
| `src/app/features/auth/`          | Login page                                                      |
| `src/app/features/leave/`         | `LeaveStore`, My leave, Apply, balance card                     |
| `src/app/features/approvals/`     | Lazy, manager-only approvals with optimistic updates            |
| `src/app/features/notifications/` | Bell, notifications store, SSE wrapper                          |
| `src/app/testing/`                | Test helpers (fake JWT, fake EventSource)                       |
| `e2e/`                            | Playwright end-to-end and accessibility tests                   |
| `proxy.conf.json`                 | Dev server: `/api` → `localhost:8000`                           |
| `Dockerfile`, `nginx.conf`        | Docker image: build with Node, serve with nginx, forward `/api` |
