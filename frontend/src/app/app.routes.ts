import { Routes } from '@angular/router';

import { Shell } from './layout/shell';

/**
 * Route table (UI_SPEC.md §5).
 * Signed-in pages are children of the Shell, so they all share the toolbar.
 * Step 3 adds /login and the guards; steps 4-5 replace the placeholder pages.
 */
export const routes: Routes = [
  {
    path: '',
    component: Shell,
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'leave' },
      {
        path: 'leave',
        title: 'My leave · LeaveDesk',
        loadComponent: () => import('./features/leave/my-leave.page').then((m) => m.MyLeavePage),
      },
    ],
  },
  { path: '**', redirectTo: 'leave' },
];
