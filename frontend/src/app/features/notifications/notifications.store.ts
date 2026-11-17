import { computed, effect, inject, Injectable, signal, untracked } from '@angular/core';
import { retry, Subscription, timer } from 'rxjs';

import { ApiError, toApiError } from '../../core/api-error';
import { NotificationItem } from '../../core/api.types';
import { AuthService } from '../../core/auth/auth.service';
import { LoadStatus } from '../leave/leave.models';
import { NotificationsApi, PANEL_SIZE } from './notifications.api';

/** Seconds to wait before reopening the stream after the browser gave up on it. */
const RECONNECT_SECONDS = 10;

/**
 * Notifications signal store (UI_SPEC.md §5.5, UI-21 to UI-25).
 *
 * - `items` holds the most recent notifications, newest first; `unreadCount` is a computed()
 *   signal over it, so the bell badge updates by itself.
 * - When a user signs in (a token appears), it loads the list and opens one SSE connection;
 *   when they sign out or the session ends, it closes the connection and clears everything.
 * - `latest` is the most recent notification that arrived live; the bell shows a snackbar for
 *   it and the shell reloads leave data when it is a decision.
 */
@Injectable({ providedIn: 'root' })
export class NotificationsStore {
  private readonly api = inject(NotificationsApi);
  private readonly auth = inject(AuthService);

  private readonly _items = signal<NotificationItem[]>([]);
  private readonly _status = signal<LoadStatus>('idle');
  private readonly _error = signal<ApiError | null>(null);
  private readonly _latest = signal<NotificationItem | null>(null);
  private readonly _streamOpen = signal(false);

  private streamSub?: Subscription;
  private loadSub?: Subscription;

  readonly items = this._items.asReadonly();
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly latest = this._latest.asReadonly();
  /** True while an SSE connection is held open (for tests and debugging). */
  readonly streamOpen = this._streamOpen.asReadonly();

  readonly unreadCount = computed(() => this._items().filter((n) => !n.read).length);
  readonly isEmpty = computed(() => this._status() === 'success' && this._items().length === 0);

  constructor() {
    // React to sign-in and sign-out. untracked() keeps the work inside from adding more
    // signals to this effect: it must re-run only when the token changes.
    effect(() => {
      const token = this.auth.token();
      untracked(() => {
        if (token) {
          this.load();
          this.connect(token);
        } else {
          this.disconnect();
          this.reset();
        }
      });
    });
  }

  load(): void {
    this.loadSub?.unsubscribe();
    this._status.set('loading');
    this._error.set(null);
    this.loadSub = this.api.recent().subscribe({
      next: (page) => {
        this._items.set(page.items);
        this._status.set('success');
      },
      error: (err: unknown) => {
        this._error.set(toApiError(err));
        this._status.set('error');
      },
    });
  }

  /** Marks everything read on the server, then locally (UI-23). Does nothing if all are read. */
  markAllRead(): void {
    if (this.unreadCount() === 0) {
      return;
    }
    this.api.markAllRead().subscribe({
      next: () => this._items.update((items) => items.map((n) => ({ ...n, read: true }))),
      error: () => undefined, // the badge simply stays as it was; the next open tries again
    });
  }

  private connect(token: string): void {
    this.disconnect();
    this._streamOpen.set(true);
    this.streamSub = this.api
      .stream(token)
      .pipe(retry({ delay: () => timer(RECONNECT_SECONDS * 1000) }))
      .subscribe((notification) => this.receive(notification));
  }

  private receive(notification: NotificationItem): void {
    this._items.update((items) =>
      [notification, ...items.filter((n) => n.id !== notification.id)].slice(0, PANEL_SIZE),
    );
    this._latest.set(notification);
  }

  private disconnect(): void {
    this.streamSub?.unsubscribe();
    this.streamSub = undefined;
    this._streamOpen.set(false);
  }

  private reset(): void {
    this.loadSub?.unsubscribe();
    this._items.set([]);
    this._status.set('idle');
    this._error.set(null);
    this._latest.set(null);
  }
}
