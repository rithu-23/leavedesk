import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { NotificationItem } from '../../core/api.types';
import { AuthService } from '../../core/auth/auth.service';
import { FakeEventSource } from '../../testing/fake-event-source';
import { signInAs, TEST_ROUTES } from '../../testing/fake-token';
import { NotificationsStore } from './notifications.store';

function note(id: string, read: boolean, event = 'approved'): NotificationItem {
  return { id, event, message: `Message ${id}`, read, created_at: '2026-11-17T10:00:00Z' };
}

async function setup(items: NotificationItem[]) {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
  signInAs('E-ANA', 'employee');
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(TEST_ROUTES)],
  });
  const store = TestBed.inject(NotificationsStore);
  const http = TestBed.inject(HttpTestingController);
  TestBed.tick(); // runs the sign-in effect: load + open the stream
  http
    .expectOne((r) => r.url === '/api/notifications')
    .flush({ items, total: items.length, limit: 20, offset: 0 });
  return { store, http, auth: TestBed.inject(AuthService) };
}

describe('NotificationsStore', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it('counts unread notifications with computed() (UI-21)', async () => {
    const { store } = await setup([
      note('N-1', false),
      note('N-2', false),
      note('N-3', false),
      note('N-4', true),
      note('N-5', true),
    ]);
    expect(store.unreadCount()).toBe(3);
  });

  it('opens exactly one stream with the token in the URL (UI-25)', async () => {
    await setup([]);
    const open = FakeEventSource.open();
    expect(open).toHaveLength(1);
    expect(open[0].url).toMatch(/^\/api\/notifications\/stream\?access_token=.+\..+\..+$/);
  });

  it('adds a live notification to the top and raises the count (UI-22)', async () => {
    const { store } = await setup([note('N-1', true)]);

    FakeEventSource.open()[0].emit('notification', note('N-2', false));

    expect(store.items().map((n) => n.id)).toEqual(['N-2', 'N-1']);
    expect(store.unreadCount()).toBe(1);
    expect(store.latest()?.id).toBe('N-2');
  });

  it('marks everything read through the API (UI-23)', async () => {
    const { store, http } = await setup([note('N-1', false), note('N-2', false)]);

    store.markAllRead();
    const req = http.expectOne('/api/notifications/read-all');
    expect(req.request.method).toBe('POST');
    req.flush({ updated: 2 });

    expect(store.unreadCount()).toBe(0);
  });

  it('closes the stream and clears the list on sign-out (UI-25)', async () => {
    const { store, auth } = await setup([note('N-1', false)]);

    auth.logout();
    TestBed.tick();

    expect(FakeEventSource.open()).toHaveLength(0);
    expect(store.items()).toEqual([]);
    expect(store.streamOpen()).toBe(false);
  });
});
