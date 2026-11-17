import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { render, screen } from '@testing-library/angular';

import { FakeEventSource } from '../testing/fake-event-source';
import { fakeToken, TEST_ROUTES } from '../testing/fake-token';
import { Shell } from './shell';

async function renderShellAs(role: 'employee' | 'manager') {
  vi.stubGlobal('EventSource', FakeEventSource);
  sessionStorage.setItem('leavedesk.token', fakeToken(role === 'manager' ? 'E-MO' : 'E-ANA', role));
  const result = await render(Shell, {
    providers: [provideRouter(TEST_ROUTES), provideHttpClient(), provideHttpClientTesting()],
  });
  sessionStorage.clear();
  return result;
}

describe('Shell', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows the brand, the menu button and an employee without Approvals (UI-2)', async () => {
    const { container } = await renderShellAs('employee');

    expect(screen.getByRole('link', { name: 'LeaveDesk' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toBeTruthy();
    // The link bar is hidden below 600 px by CSS, and jsdom has no real screen width,
    // so check it in the DOM rather than through the accessibility tree.
    const nav = container.querySelector('nav[aria-label="Main"]');
    expect(nav?.textContent).toContain('My leave');
    expect(nav?.textContent).not.toContain('Approvals');
  });

  it('shows the Approvals link to a manager', async () => {
    const { container } = await renderShellAs('manager');
    const nav = container.querySelector('nav[aria-label="Main"]');
    expect(nav?.textContent).toContain('Approvals');
  });
});
