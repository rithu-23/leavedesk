import { Routes } from '@angular/router';

import { authGuard, guestGuard, roleGuard } from './core/auth/auth.guards';
import { Shell } from './layout/shell';

/**
 * Route table (UI_SPEC.md §5).
 * - /login is for signed-out users only.
 * - Every other page is a child of the Shell (shared toolbar) and needs a signed-in user.
 * - /approvals is lazy-loaded and matches only for managers (canMatch), so employees
 *   never download its code.
 */
export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in · LeaveDesk',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login.page').then((m) => m.LoginPage),
  },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'leave' },
      {
        path: 'leave',
        title: 'My leave · LeaveDesk',
        loadComponent: () => import('./features/leave/my-leave.page').then((m) => m.MyLeavePage),
      },
      {
        path: 'approvals',
        canMatch: [roleGuard('manager')],
        loadChildren: () =>
          import('./features/approvals/approvals.routes').then((m) => m.APPROVALS_ROUTES),
      },
    ],
  },
  { path: '**', redirectTo: 'leave' },
];
