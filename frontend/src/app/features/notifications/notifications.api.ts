import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { NotificationItem, Page } from '../../core/api.types';
import { fromEventSource } from './sse';

/** How many recent notifications the panel shows. */
export const PANEL_SIZE = 20;

/** Data access for notifications (API_SPEC.md §3 and §6). */
@Injectable({ providedIn: 'root' })
export class NotificationsApi {
  private readonly http = inject(HttpClient);

  recent(): Observable<Page<NotificationItem>> {
    const params = new HttpParams().set('limit', PANEL_SIZE);
    return this.http.get<Page<NotificationItem>>('/api/notifications', { params });
  }

  markAllRead(): Observable<{ updated: number }> {
    return this.http.post<{ updated: number }>('/api/notifications/read-all', null);
  }

  /**
   * The live stream. EventSource can't send an Authorization header, so the token goes in
   * the query string (the API accepts ?access_token= on this endpoint only).
   */
  stream(token: string): Observable<NotificationItem> {
    const url = `/api/notifications/stream?access_token=${encodeURIComponent(token)}`;
    return fromEventSource<NotificationItem>(url, 'notification');
  }
}
