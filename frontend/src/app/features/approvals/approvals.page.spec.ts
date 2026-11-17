import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { render, screen, waitFor } from '@testing-library/angular';
import userEvent from '@testing-library/user-event';

import { LeaveRequest } from '../../core/api.types';
import { signInAs, TEST_ROUTES } from '../../testing/fake-token';
import { ApprovalsApi } from './approvals.api';
import { ApprovalsPage } from './approvals.page';
import { ApprovalsStore } from './approvals.store';

const REQUEST: LeaveRequest = {
  id: 'LR-1',
  employee_id: 'E-ANA',
  leave_type: 'CASUAL',
  start_date: '2027-01-11',
  end_date: '2027-01-12',
  half_day: false,
  reason: 'Moving house',
  status: 'pending',
  days: '2.0',
  version: 2,
  created_at: '2026-11-17T10:00:00Z',
  decided_by: null,
  decision_note: null,
};

function typeInto(field: HTMLTextAreaElement, text: string): void {
  field.value = text;
  field.dispatchEvent(new Event('input'));
}

async function renderPage(items: LeaveRequest[] = [REQUEST]) {
  signInAs('E-MO', 'manager');
  await render(ApprovalsPage, {
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter(TEST_ROUTES),
      ApprovalsApi,
      ApprovalsStore,
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  http
    .expectOne((r) => r.url === '/api/leave-requests')
    .flush({ items, total: items.length, limit: 100, offset: 0 });
  return { http, user: userEvent.setup() };
}

describe('ApprovalsPage', () => {
  afterEach(() => sessionStorage.clear());

  it('approves through the confirm dialog (UI-18)', async () => {
    const { http, user } = await renderPage();
    expect(await screen.findByText('Moving house')).toBeTruthy();
    expect(screen.getByText('Casual')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: 'Approve E-ANA 2027-01-11' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Approve 2 day(s) of casual leave for E-ANA');
    await user.click(screen.getByRole('button', { name: 'Approve' }));

    // The dialog closes with an animation, so wait for the request to be sent.
    const req = await waitFor(() => http.expectOne('/api/leave-requests/LR-1/approve'));
    expect(req.request.headers.get('If-Match')).toBe('2');
    req.flush({ ...REQUEST, status: 'approved', version: 3 });
    expect(await screen.findByText('Nothing waiting for approval')).toBeTruthy();
  });

  it('keeps Reject disabled until a reason is typed (UI-19)', async () => {
    const { http, user } = await renderPage();
    await user.click(await screen.findByRole('button', { name: 'Reject E-ANA 2027-01-11' }));
    await screen.findByRole('dialog');

    const reject = screen.getByRole('button', { name: 'Reject' }) as HTMLButtonElement;
    const reason = screen.getByLabelText('Reason') as HTMLTextAreaElement;
    expect(reject.disabled).toBe(true);

    // Typed with a plain DOM input event: Testing Library's typing helper re-runs change
    // detection inside each key event, which clashes with the open dialog (NG0101).
    typeInto(reason, '   ');
    await waitFor(() => expect(reject.disabled).toBe(true));
    typeInto(reason, 'Team is short that week');
    await waitFor(() => expect(reject.disabled).toBe(false));
    await user.click(reject);

    const req = await waitFor(() => http.expectOne('/api/leave-requests/LR-1/reject'));
    expect(req.request.body).toEqual({ reason: 'Team is short that week' });
  });

  it('shows the empty state when nothing is pending', async () => {
    await renderPage([]);
    expect(await screen.findByText('Nothing waiting for approval')).toBeTruthy();
  });
});
