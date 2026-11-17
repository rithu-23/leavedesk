import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { LeaveRequest, Page } from '../../core/api.types';

/** Most pending requests the screen loads at once (the API allows up to 100 per page). */
export const PENDING_LIMIT = 100;

/**
 * Data access for approvals. Approve and reject send If-Match with the version the manager
 * saw, so if the request changed in the meantime the API answers 409 CONCURRENT_UPDATE
 * instead of acting on stale data (Capstone 3 optimistic locking).
 */
@Injectable()
export class ApprovalsApi {
  private readonly http = inject(HttpClient);

  pending(): Observable<LeaveRequest[]> {
    const params = new HttpParams()
      .set('status', 'pending')
      .set('sort', 'start_date')
      .set('limit', PENDING_LIMIT);
    return this.http
      .get<Page<LeaveRequest>>('/api/leave-requests', { params })
      .pipe(map((page) => page.items.map((r) => ({ ...r, days: Number(r.days) }))));
  }

  approve(request: LeaveRequest): Observable<LeaveRequest> {
    return this.http.post<LeaveRequest>(
      `/api/leave-requests/${encodeURIComponent(request.id)}/approve`,
      null,
      { headers: ifMatch(request) },
    );
  }

  reject(request: LeaveRequest, reason: string): Observable<LeaveRequest> {
    return this.http.post<LeaveRequest>(
      `/api/leave-requests/${encodeURIComponent(request.id)}/reject`,
      { reason },
      { headers: ifMatch(request) },
    );
  }
}

function ifMatch(request: LeaveRequest): HttpHeaders {
  return new HttpHeaders({ 'If-Match': String(request.version) });
}
