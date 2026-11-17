import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { LeaveRequest } from '../../core/api.types';
import { signInAs, TEST_ROUTES } from '../../testing/fake-token';
import { LeaveStore } from './leave.store';

const REQUEST: LeaveRequest = {
  id: 'LR-1',
  employee_id: 'E-ANA',
  leave_type: 'ANNUAL',
  start_date: '2027-01-11',
  end_date: '2027-01-13',
  half_day: false,
  reason: 'Family trip',
  status: 'pending',
  days: '3.0',
  version: 1,
  created_at: '2026-11-17T10:00:00Z',
  decided_by: null,
  decision_note: null,
};

function setup(): { store: LeaveStore; http: HttpTestingController } {
  signInAs('E-ANA', 'employee');
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(TEST_ROUTES)],
  });
  return { store: TestBed.inject(LeaveStore), http: TestBed.inject(HttpTestingController) };
}

describe('LeaveStore', () => {
  afterEach(() => sessionStorage.clear());

  it('goes loading → success and keeps the page of requests (UI-9)', () => {
    const { store, http } = setup();

    store.loadRequests();
    expect(store.status()).toBe('loading');
    expect(store.loading()).toBe(true);

    const req = http.expectOne((r) => r.url === '/api/leave-requests');
    expect(req.request.params.get('employee_id')).toBe('E-ANA');
    expect(req.request.params.get('sort')).toBe('-start_date');
    expect(req.request.params.get('limit')).toBe('10');
    expect(req.request.params.get('offset')).toBe('0');
    req.flush({ items: [REQUEST], total: 1, limit: 10, offset: 0 });

    expect(store.status()).toBe('success');
    expect(store.requests()[0].days).toBe(3);
    expect(store.total()).toBe(1);
  });

  it('goes loading → error with the API message', () => {
    const { store, http } = setup();

    store.loadRequests();
    http
      .expectOne((r) => r.url === '/api/leave-requests')
      .flush(
        { error: { code: 'DATABASE_BUSY', message: 'The database is busy.' } },
        { status: 503, statusText: 'Service Unavailable' },
      );

    expect(store.status()).toBe('error');
    expect(store.error()?.message).toBe('The database is busy.');
  });

  it('converts the balance to numbers and derives totals with computed() (UI-8)', () => {
    const { store, http } = setup();

    store.loadBalance();
    http.expectOne('/api/employees/E-ANA/balance').flush([
      { leave_type: 'CASUAL', entitlement: '6.0', used: '0.0', pending: '2.0', available: '4.0' },
      { leave_type: 'SICK', entitlement: '12.0', used: '0.0', pending: '11.0', available: '1.0' },
      { leave_type: 'ANNUAL', entitlement: '18.0', used: '3.0', pending: '3.0', available: '12.0' },
    ]);

    expect(store.balance().map((b) => b.leaveType)).toEqual(['ANNUAL', 'SICK', 'CASUAL']);
    expect(store.annual()?.available).toBe(12);
    expect(store.totalAvailable()).toBe(17);
    expect(store.lowAnnualBalance()).toBe(false);
  });

  it('filtering by status reloads from the first page (UI-10)', () => {
    const { store, http } = setup();
    store.setPage(2, 10);
    http
      .expectOne((r) => r.url === '/api/leave-requests')
      .flush({
        items: [],
        total: 0,
        limit: 10,
        offset: 20,
      });

    store.setStatusFilter('pending');

    const req = http.expectOne((r) => r.url === '/api/leave-requests');
    expect(req.request.params.get('status')).toBe('pending');
    expect(req.request.params.get('offset')).toBe('0');
  });
});
