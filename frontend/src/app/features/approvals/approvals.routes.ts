import { Routes } from '@angular/router';

import { ApprovalsPage } from './approvals.page';

/**
 * Routes of the approvals feature. This whole file (and everything it imports) is a
 * separate bundle that the browser downloads only when a manager opens /approvals.
 */
export const APPROVALS_ROUTES: Routes = [
  { path: '', title: 'Approvals · LeaveDesk', component: ApprovalsPage },
];
