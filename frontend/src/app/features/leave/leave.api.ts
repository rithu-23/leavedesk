import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { BalanceDto, LeaveRequest, Page } from '../../core/api.types';
import { Balance, LeaveQuery, NewLeaveRequest } from './leave.models';

/**
 * Data-access layer for leave: the only place that knows the leave URLs.
 * It converts API shapes into UI shapes (decimal strings → numbers) so nothing else has to.
 */
@Injectable({ providedIn: 'root' })
export class LeaveApi {
  private readonly http = inject(HttpClient);

  balance(employeeId: string): Observable<Balance[]> {
    return this.http
      .get<BalanceDto[]>(`/api/employees/${encodeURIComponent(employeeId)}/balance`)
      .pipe(
        map((rows) =>
          rows.map((row) => ({
            leaveType: row.leave_type,
            entitlement: Number(row.entitlement),
            used: Number(row.used),
            pending: Number(row.pending),
            available: Number(row.available),
          })),
        ),
      );
  }

  list(employeeId: string, query: LeaveQuery): Observable<Page<LeaveRequest>> {
    let params = new HttpParams()
      .set('employee_id', employeeId)
      .set('sort', '-start_date')
      .set('limit', query.pageSize)
      .set('offset', query.pageIndex * query.pageSize);
    if (query.status !== 'all') {
      params = params.set('status', query.status);
    }
    return this.http
      .get<Page<LeaveRequest>>('/api/leave-requests', { params })
      .pipe(map((page) => ({ ...page, items: page.items.map(withNumericDays) })));
  }

  /** The Idempotency-Key makes a retried or double-clicked submit create only one request. */
  create(body: NewLeaveRequest, idempotencyKey: string): Observable<LeaveRequest> {
    const headers = new HttpHeaders({ 'Idempotency-Key': idempotencyKey });
    return this.http
      .post<LeaveRequest>('/api/leave-requests', body, { headers })
      .pipe(map(withNumericDays));
  }

  cancel(id: string): Observable<unknown> {
    return this.http.delete(`/api/leave-requests/${encodeURIComponent(id)}`);
  }
}

function withNumericDays(request: LeaveRequest): LeaveRequest {
  return { ...request, days: Number(request.days) };
}
