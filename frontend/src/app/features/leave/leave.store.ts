import { computed, effect, inject, Injectable, signal } from '@angular/core';
import { Observable, Subscription, tap } from 'rxjs';

import { ApiError, toApiError } from '../../core/api-error';
import { LeaveRequest, LeaveStatus } from '../../core/api.types';
import { AuthService } from '../../core/auth/auth.service';
import { LEAVE_TYPES } from '../../shared/leave-type';
import { LeaveApi } from './leave.api';
import { Balance, LeaveQuery, LoadStatus, NewLeaveRequest } from './leave.models';

const FIRST_PAGE: LeaveQuery = { status: 'all', pageIndex: 0, pageSize: 10 };

/**
 * Feature signal store for the signed-in user's leave (UI_SPEC.md §5.2, §6).
 *
 * - Server state (requests, total, balance) and UI state (the current filter and page) live
 *   in private signals; screens read the public read-only versions and computed values.
 * - Each list has a LoadStatus: 'loading' while waiting, then 'success' or 'error'.
 * - RxJS is used only to talk to HttpClient; every result is written into a signal.
 * - providedIn: 'root' means one shared instance, so the apply page and (in step 6)
 *   notifications can tell the same store to refresh.
 */
@Injectable({ providedIn: 'root' })
export class LeaveStore {
  private readonly api = inject(LeaveApi);
  private readonly auth = inject(AuthService);

  // ---- state ----
  private readonly _requests = signal<LeaveRequest[]>([]);
  private readonly _total = signal(0);
  private readonly _query = signal<LeaveQuery>(FIRST_PAGE);
  private readonly _status = signal<LoadStatus>('idle');
  private readonly _error = signal<ApiError | null>(null);

  private readonly _balance = signal<Balance[]>([]);
  private readonly _balanceStatus = signal<LoadStatus>('idle');
  private readonly _balanceError = signal<ApiError | null>(null);

  private listSub?: Subscription;
  private balanceSub?: Subscription;

  // ---- read-only views for components ----
  readonly requests = this._requests.asReadonly();
  readonly total = this._total.asReadonly();
  readonly query = this._query.asReadonly();
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly balance = this._balance.asReadonly();
  readonly balanceStatus = this._balanceStatus.asReadonly();
  readonly balanceError = this._balanceError.asReadonly();

  // ---- derived state (recomputed automatically when the signals above change) ----
  readonly loading = computed(() => this._status() === 'loading');
  readonly isEmpty = computed(() => this._status() === 'success' && this._requests().length === 0);
  readonly annual = computed(() => this._balance().find((b) => b.leaveType === 'ANNUAL'));
  readonly totalAvailable = computed(() =>
    this._balance().reduce((sum, row) => sum + row.available, 0),
  );
  /** Annual leave below 2 days gets a warning on the balance card. */
  readonly lowAnnualBalance = computed(() => {
    const annual = this.annual();
    return annual !== undefined && annual.available < 2;
  });

  constructor() {
    // When the user signs out, forget their data so the next user starts clean.
    effect(() => {
      if (!this.auth.isLoggedIn()) {
        this.reset();
      }
    });
  }

  /** Loads the current page of requests. A newer load cancels an older one still running. */
  loadRequests(): void {
    const employeeId = this.auth.user()?.employeeId;
    if (!employeeId) {
      return;
    }
    this.listSub?.unsubscribe();
    this._status.set('loading');
    this._error.set(null);
    this.listSub = this.api.list(employeeId, this._query()).subscribe({
      next: (page) => {
        this._requests.set(page.items);
        this._total.set(page.total);
        this._status.set('success');
      },
      error: (err: unknown) => {
        this._error.set(toApiError(err));
        this._status.set('error');
      },
    });
  }

  loadBalance(): void {
    const employeeId = this.auth.user()?.employeeId;
    if (!employeeId) {
      return;
    }
    this.balanceSub?.unsubscribe();
    this._balanceStatus.set('loading');
    this._balanceError.set(null);
    this.balanceSub = this.api.balance(employeeId).subscribe({
      next: (rows) => {
        // Always Annual, Sick, Casual, whatever order the API returns.
        const order = (b: Balance) => {
          const i = LEAVE_TYPES.indexOf(b.leaveType);
          return i === -1 ? LEAVE_TYPES.length : i;
        };
        this._balance.set([...rows].sort((a, b) => order(a) - order(b)));
        this._balanceStatus.set('success');
      },
      error: (err: unknown) => {
        this._balanceError.set(toApiError(err));
        this._balanceStatus.set('error');
      },
    });
  }

  /** Reloads both the table and the balance (after submit, cancel or a notification). */
  refresh(): void {
    this.loadRequests();
    this.loadBalance();
  }

  /** Changing the filter goes back to the first page (UI-10). */
  setStatusFilter(status: LeaveStatus | 'all'): void {
    this._query.update((q) => ({ ...q, status, pageIndex: 0 }));
    this.loadRequests();
  }

  setPage(pageIndex: number, pageSize: number): void {
    this._query.update((q) => ({ ...q, pageIndex, pageSize }));
    this.loadRequests();
  }

  /** Submits a new request; on success the table and balance reload. Errors go to the caller. */
  submit(body: NewLeaveRequest, idempotencyKey: string): Observable<LeaveRequest> {
    return this.api.create(body, idempotencyKey).pipe(tap(() => this.refresh()));
  }

  /** Cancels a pending request; on success the table and balance reload. */
  cancel(id: string): Observable<unknown> {
    return this.api.cancel(id).pipe(tap(() => this.refresh()));
  }

  private reset(): void {
    this.listSub?.unsubscribe();
    this.balanceSub?.unsubscribe();
    this._requests.set([]);
    this._total.set(0);
    this._query.set(FIRST_PAGE);
    this._status.set('idle');
    this._error.set(null);
    this._balance.set([]);
    this._balanceStatus.set('idle');
    this._balanceError.set(null);
  }
}
