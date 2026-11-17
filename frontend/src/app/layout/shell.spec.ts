import { provideRouter } from '@angular/router';
import { render, screen } from '@testing-library/angular';

import { Shell } from './shell';

describe('Shell', () => {
  it('shows the LeaveDesk brand, the main navigation and the menu button', async () => {
    const { container } = await render(Shell, { providers: [provideRouter([])] });

    expect(screen.getByRole('link', { name: 'LeaveDesk' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toBeTruthy();
    // The link bar is hidden below 600 px by CSS, and jsdom has no real screen width,
    // so check it in the DOM rather than through the accessibility tree.
    const nav = container.querySelector('nav[aria-label="Main"]');
    expect(nav?.textContent).toContain('My leave');
  });
});
