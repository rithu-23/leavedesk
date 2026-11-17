import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { render, screen, within } from '@testing-library/angular';

import { LeaveRequest } from '../../core/api.types';
import { signInAs, TEST_ROUTES } from '../../testing/fake-token';
import { MyLeavePage } from './my-leave.page';

const BALANCE = [
  { leave_type: 'ANNUAL', entitlement: '20.0', used: '5.0', pending: '3.0', available: '12.0' },
  { leave_type: 'SICK', entitlement: '12.0', used: '0.0', pending: '11.0', available: '1.0' },
  { leave_type: 'CASUAL', entitlement: '6.0', used: '0.0', pending: '2.0', available: '4.0' },
];

function request(
  id: string,
  status: LeaveRequest['status'],
  leaveType: LeaveRequest['leave_type'] = 'ANNUAL',
): LeaveRequest {
  return {
    id,
    employee_id: 'E-ANA',
    leave_type: leaveType,
    start_date: '2027-01-11',
    end_date: '2027-01-13',
    half_day: false,
    reason: `Reason ${id}`,
    status,
    days: '3.0',
    version: 1,
    created_at: '2026-11-17T10:00:00Z',
    decided_by: null,
    decision_note: null,
  };
}

async function renderPage() {
  signInAs('E-ANA', 'employee');
  await render(MyLeavePage, {
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(TEST_ROUTES)],
  });
  return TestBed.inject(HttpTestingController);
}

describe('MyLeavePage', () => {
  afterEach(() => sessionStorage.clear());

  it('shows the balance and the requests, with Cancel only on pending rows (UI-8, UI-9, UI-11)', async () => {
    const http = await renderPage();
    http.expectOne('/api/employees/E-ANA/balance').flush(BALANCE);
    http
      .expectOne((r) => r.url === '/api/leave-requests')
      .flush({
        items: [request('LR-1', 'pending', 'CASUAL'), request('LR-2', 'approved')],
        total: 2,
        limit: 10,
        offset: 0,
      });

    const annual = await screen.findByTestId('balance-ANNUAL');
    expect(within(annual).getByTestId('available').textContent?.trim()).toBe('12');
    expect(screen.getByText('Reason LR-1')).toBeTruthy();
    expect(screen.getByText('Reason LR-2')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Cancel' })).toHaveLength(1);
  });

  it('labels every leave type correctly, including Casual', async () => {
    const http = await renderPage();
    http.expectOne('/api/employees/E-ANA/balance').flush(BALANCE);
    http
      .expectOne((r) => r.url === '/api/leave-requests')
      .flush({ items: [request('LR-1', 'pending', 'CASUAL')], total: 1, limit: 10, offset: 0 });

    const casual = await screen.findByTestId('balance-CASUAL');
    expect(within(casual).getByRole('rowheader').textContent?.trim()).toBe('Casual');
    expect(
      within(screen.getByTestId('balance-SICK')).getByRole('rowheader').textContent?.trim(),
    ).toBe('Sick');
    // The CASUAL request row shows "Casual", never "Sick".
    const row = screen.getByText('Reason LR-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('Casual')).toBeTruthy();
    expect(within(row).queryByText('Sick')).toBeNull();
  });

  it('shows the empty state when there are no requests', async () => {
    const http = await renderPage();
    http.expectOne('/api/employees/E-ANA/balance').flush(BALANCE);
    http
      .expectOne((r) => r.url === '/api/leave-requests')
      .flush({ items: [], total: 0, limit: 10, offset: 0 });

    expect(await screen.findByText('No leave requests yet')).toBeTruthy();
  });

  it('shows an error with Retry when the list fails', async () => {
    const http = await renderPage();
    http.expectOne('/api/employees/E-ANA/balance').flush(BALANCE);
    http
      .expectOne((r) => r.url === '/api/leave-requests')
      .flush(
        { error: { code: 'DATABASE_BUSY', message: 'The database is busy.' } },
        { status: 503, statusText: 'Service Unavailable' },
      );

    expect(await screen.findByText('The database is busy.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
  });
});
