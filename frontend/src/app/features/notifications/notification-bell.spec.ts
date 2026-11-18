import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { render, screen, waitFor } from '@testing-library/angular';
import userEvent from '@testing-library/user-event';

import { NotificationItem } from '../../core/api.types';
import { FakeEventSource } from '../../testing/fake-event-source';
import { signInAs, TEST_ROUTES } from '../../testing/fake-token';
import { NotificationBell } from './notification-bell';

function note(id: string, read: boolean): NotificationItem {
  return {
    id,
    event: 'approved',
    message: `Your leave ${id} was approved`,
    read,
    created_at: '2026-11-17T10:00:00Z',
  };
}

async function renderBell(items: NotificationItem[] | 'error') {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
  signInAs('E-ANA', 'employee');
  await render(NotificationBell, {
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(TEST_ROUTES)],
  });
  const http = TestBed.inject(HttpTestingController);
  const req = http.expectOne((r) => r.url === '/api/notifications');
  if (items === 'error') {
    req.flush({ error: { code: 'X', message: 'down' } }, { status: 500, statusText: 'Error' });
  } else {
    req.flush({ items, total: items.length, limit: 20, offset: 0 });
  }
  return { http, user: userEvent.setup() };
}

describe('NotificationBell', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it('shows the unread count in the badge and the accessible name (UI-21)', async () => {
    await renderBell([
      note('N-1', false),
      note('N-2', false),
      note('N-3', false),
      note('N-4', true),
    ]);

    const bell = await screen.findByRole('button', { name: 'Notifications 3 unread' });
    expect(bell.textContent).toContain('3');
    expect(screen.getByText('3 unread notifications')).toBeTruthy();
  });

  it('opening the panel lists notifications and marks them read (UI-23)', async () => {
    const { http, user } = await renderBell([note('N-1', false)]);

    await user.click(await screen.findByRole('button', { name: 'Notifications 1 unread' }));
    expect(await screen.findByText('Your leave N-1 was approved')).toBeTruthy();

    http.expectOne('/api/notifications/read-all').flush({ updated: 1 });
    expect(await screen.findByRole('button', { name: 'Notifications 0 unread' })).toBeTruthy();
  });

  it('opens as a dialog and Close puts it away (UI-27)', async () => {
    const { user } = await renderBell([note('N-1', true)]);
    const bell = await screen.findByRole('button', { name: 'Notifications 0 unread' });
    expect(bell.getAttribute('aria-expanded')).toBe('false');

    await user.click(bell);
    expect(await screen.findByRole('dialog', { name: 'Notifications' })).toBeTruthy();
    expect(bell.getAttribute('aria-expanded')).toBe('true');

    await user.click(screen.getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('shows "No notifications" when the list is empty (UI-24)', async () => {
    const { user } = await renderBell([]);
    await user.click(await screen.findByRole('button', { name: 'Notifications 0 unread' }));
    expect(await screen.findByText('No notifications')).toBeTruthy();
  });

  it('shows an error with Retry when loading fails (UI-24)', async () => {
    const { user } = await renderBell('error');
    await user.click(await screen.findByRole('button', { name: 'Notifications 0 unread' }));
    expect(await screen.findByText("Couldn't load notifications")).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
  });
});
