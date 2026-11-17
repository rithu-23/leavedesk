import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ApiError } from '../../core/api-error';
import { LeaveRequest } from '../../core/api.types';
import { signInAs, TEST_ROUTES } from '../../testing/fake-token';
import { ApprovalsApi } from './approvals.api';
import { ApprovalsStore } from './approvals.store';

function pending(id: string, employeeId = 'E-ANA', version = 1): LeaveRequest {
  return {
    id,
    employee_id: employeeId,
    leave_type: 'ANNUAL',
    start_date: '2027-01-11',
    end_date: '2027-01-13',
    half_day: false,
    reason: `Reason ${id}`,
    status: 'pending',
    days: '3.0',
    version,
    created_at: '2026-11-17T10:00:00Z',
    decided_by: null,
    decision_note: null,
  };
}

function setup() {
  signInAs('E-MO', 'manager');
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter(TEST_ROUTES),
      ApprovalsApi,
      ApprovalsStore,
    ],
  });
  const store = TestBed.inject(ApprovalsStore);
  const http = TestBed.inject(HttpTestingController);
  const loadWith = (items: LeaveRequest[]) => {
    store.load();
    http
      .expectOne((r) => r.url === '/api/leave-requests' && r.params.get('status') === 'pending')
      .flush({ items, total: items.length, limit: 100, offset: 0 });
  };
  return { store, http, loadWith };
}

describe('ApprovalsStore', () => {
  afterEach(() => sessionStorage.clear());

  it("lists reports' pending requests oldest first, without the manager's own (UI-17)", () => {
    const { store, http } = setup();
    store.load();
    const req = http.expectOne((r) => r.url === '/api/leave-requests');
    expect(req.request.params.get('sort')).toBe('start_date');
    req.flush({
      items: [pending('LR-1'), pending('LR-MINE', 'E-MO'), pending('LR-2')],
      total: 3,
      limit: 100,
      offset: 0,
    });

    expect(store.items().map((r) => r.id)).toEqual(['LR-1', 'LR-2']);
    expect(store.count()).toBe(2);
  });

  it('removes the row at once and sends If-Match with the version (UI-18)', () => {
    const { store, http, loadWith } = setup();
    loadWith([pending('LR-1', 'E-ANA', 4), pending('LR-2')]);

    store.approve(store.items()[0]).subscribe();

    expect(store.items().map((r) => r.id)).toEqual(['LR-2']);
    const req = http.expectOne('/api/leave-requests/LR-1/approve');
    expect(req.request.headers.get('If-Match')).toBe('4');
    req.flush({ ...pending('LR-1'), status: 'approved', version: 5 });
    expect(store.items().map((r) => r.id)).toEqual(['LR-2']);
  });

  it('puts the row back in its place when the API refuses (UI-20)', () => {
    const { store, http, loadWith } = setup();
    loadWith([pending('LR-1'), pending('LR-2'), pending('LR-3')]);
    let error: ApiError | undefined;

    store.reject(store.items()[1], 'Team is short that week').subscribe({
      error: (e: ApiError) => (error = e),
    });
    expect(store.items().map((r) => r.id)).toEqual(['LR-1', 'LR-3']);

    const req = http.expectOne('/api/leave-requests/LR-2/reject');
    expect(req.request.body).toEqual({ reason: 'Team is short that week' });
    req.flush(
      { error: { code: 'FORBIDDEN', message: 'E-MO is not the manager of E-ANA.' } },
      { status: 403, statusText: 'Forbidden' },
    );

    expect(store.items().map((r) => r.id)).toEqual(['LR-1', 'LR-2', 'LR-3']);
    expect(error?.message).toBe('E-MO is not the manager of E-ANA.');
  });

  it('reloads the list after a 409 concurrent update (UI-20)', () => {
    const { store, http, loadWith } = setup();
    loadWith([pending('LR-1')]);

    store.approve(store.items()[0]).subscribe({ error: () => undefined });
    http.expectOne('/api/leave-requests/LR-1/approve').flush(
      {
        error: { code: 'CONCURRENT_UPDATE', message: 'The request was changed by someone else.' },
      },
      { status: 409, statusText: 'Conflict' },
    );

    http
      .expectOne((r) => r.url === '/api/leave-requests' && r.params.get('status') === 'pending')
      .flush({ items: [], total: 0, limit: 100, offset: 0 });
    expect(store.isEmpty()).toBe(true);
  });
});
