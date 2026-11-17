import { computed, inject, Injectable, signal } from '@angular/core';
import { catchError, map, Observable, throwError } from 'rxjs';

import { ApiError, toApiError } from '../../core/api-error';
import { LeaveRequest } from '../../core/api.types';
import { AuthService } from '../../core/auth/auth.service';
import { LoadStatus } from '../leave/leave.models';
import { ApprovalsApi } from './approvals.api';

/**
 * Feature signal store for the manager's approval queue (UI_SPEC.md §5.4, UI-17 to UI-20).
 * It is provided by the approvals routes, so it exists only while a manager is on this
 * feature and its code stays in the lazy bundle.
 *
 * Optimistic update: approve/reject remove the row at once, before the API answers, so the
 * screen feels instant. If the API fails, the row is put back where it was; on 409 (someone
 * else changed it, or it is no longer pending) the list also reloads from the server.
 */
@Injectable()
export class ApprovalsStore {
  private readonly api = inject(ApprovalsApi);
  private readonly auth = inject(AuthService);

  private readonly _items = signal<LeaveRequest[]>([]);
  private readonly _status = signal<LoadStatus>('idle');
  private readonly _error = signal<ApiError | null>(null);

  readonly items = this._items.asReadonly();
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly loading = computed(() => this._status() === 'loading');
  readonly isEmpty = computed(() => this._status() === 'success' && this._items().length === 0);
  readonly count = computed(() => this._items().length);

  load(): void {
    const me = this.auth.user()?.employeeId;
    this._status.set('loading');
    this._error.set(null);
    this.api.pending().subscribe({
      next: (items) => {
        // The API lists the manager's own requests too; a manager can't approve those (BR-6).
        this._items.set(items.filter((r) => r.employee_id !== me));
        this._status.set('success');
      },
      error: (err: unknown) => {
        this._error.set(toApiError(err));
        this._status.set('error');
      },
    });
  }

  approve(request: LeaveRequest): Observable<void> {
    return this.decide(request, this.api.approve(request));
  }

  reject(request: LeaveRequest, reason: string): Observable<void> {
    return this.decide(request, this.api.reject(request, reason));
  }

  /** Removes the row now; restores it (and reloads on 409) if the call fails. */
  private decide(request: LeaveRequest, call: Observable<LeaveRequest>): Observable<void> {
    const index = this._items().findIndex((r) => r.id === request.id);
    this._items.update((items) => items.filter((r) => r.id !== request.id));

    return call.pipe(
      map(() => undefined),
      catchError((err: unknown) => {
        const apiError = toApiError(err);
        this._items.update((items) => {
          const restored = [...items];
          restored.splice(index < 0 ? restored.length : index, 0, request);
          return restored;
        });
        if (apiError.status === 409) {
          this.load();
        }
        return throwError(() => apiError);
      }),
    );
  }
}
