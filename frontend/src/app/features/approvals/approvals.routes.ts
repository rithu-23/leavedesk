import { Routes } from '@angular/router';

import { ApprovalsApi } from './approvals.api';
import { ApprovalsPage } from './approvals.page';
import { ApprovalsStore } from './approvals.store';

/**
 * Routes of the approvals feature. This whole file (and everything it imports) is a
 * separate bundle that the browser downloads only when a manager opens /approvals.
 * The store and API service are provided here, so they live with the feature.
 */
export const APPROVALS_ROUTES: Routes = [
  {
    path: '',
    title: 'Approvals · LeaveDesk',
    providers: [ApprovalsApi, ApprovalsStore],
    component: ApprovalsPage,
  },
];
