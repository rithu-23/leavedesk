import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { render, screen } from '@testing-library/angular';
import userEvent from '@testing-library/user-event';

import { fakeToken, TEST_ROUTES } from '../../testing/fake-token';
import { LoginPage } from './login.page';

async function renderLogin() {
  sessionStorage.clear();
  await render(LoginPage, {
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(TEST_ROUTES)],
  });
  return {
    user: userEvent.setup(),
    http: TestBed.inject(HttpTestingController),
    submit: () => screen.getByRole('button', { name: 'Sign in' }) as HTMLButtonElement,
  };
}

describe('LoginPage', () => {
  it('keeps Sign in disabled until both fields are valid (UI-1)', async () => {
    const { user, submit } = await renderLogin();
    expect(submit().disabled).toBe(true);

    await user.type(screen.getByLabelText('Email'), 'not-an-email');
    await user.type(screen.getByLabelText('Password'), 'secret');
    expect(submit().disabled).toBe(true);

    await user.clear(screen.getByLabelText('Email'));
    await user.type(screen.getByLabelText('Email'), 'ana@leavedesk.test');
    expect(submit().disabled).toBe(false);
  });

  it('shows one generic message when the API answers 401 (UI-3)', async () => {
    const { user, http, submit } = await renderLogin();
    await user.type(screen.getByLabelText('Email'), 'ana@leavedesk.test');
    await user.type(screen.getByLabelText('Password'), 'wrong');
    await user.click(submit());

    http
      .expectOne('/api/auth/login')
      .flush(
        { error: { code: 'UNAUTHENTICATED', message: 'Invalid credentials' } },
        { status: 401, statusText: 'Unauthorized' },
      );

    expect((await screen.findByRole('alert')).textContent).toContain('Invalid email or password.');
  });

  it('shows the lockout rule after 3 failed attempts in a row (UI-3)', async () => {
    const { user, http } = await renderLogin();
    await user.type(screen.getByLabelText('Email'), 'ana@leavedesk.test');
    await user.type(screen.getByLabelText('Password'), 'wrong');

    for (let attempt = 1; attempt <= 3; attempt++) {
      expect(screen.queryByText(/sign-in is paused for 15 minutes/)).toBeNull();
      // Wait for the button to show "Sign in" again after the previous attempt.
      await user.click(await screen.findByRole('button', { name: 'Sign in' }));
      http
        .expectOne('/api/auth/login')
        .flush(
          { error: { code: 'UNAUTHENTICATED', message: 'Invalid credentials' } },
          { status: 401, statusText: 'Unauthorized' },
        );
    }

    expect(
      await screen.findByText('After 5 failed attempts, sign-in is paused for 15 minutes.'),
    ).toBeTruthy();
  });

  it('goes to /leave after a successful sign-in (UI-2)', async () => {
    const { user, http, submit } = await renderLogin();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    await user.type(screen.getByLabelText('Email'), 'ana@leavedesk.test');
    await user.type(screen.getByLabelText('Password'), 'secret');
    await user.click(submit());

    http.expectOne('/api/auth/login').flush({
      access_token: fakeToken('E-ANA', 'employee'),
      token_type: 'bearer',
      expires_in: 1800,
    });

    expect(navigate).toHaveBeenCalledWith('/leave');
  });
});
