import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { render, screen } from '@testing-library/angular';
import userEvent from '@testing-library/user-event';

import { signInAs, TEST_ROUTES } from '../../testing/fake-token';
import { ApplyPage } from './apply.page';

async function renderApply() {
  signInAs('E-ANA', 'employee');
  await render(ApplyPage, {
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(TEST_ROUTES)],
  });
  const user = userEvent.setup();
  const fill = async (start: string, end: string, reason = 'Family trip') => {
    await user.type(screen.getByLabelText('Start date'), start);
    await user.type(screen.getByLabelText('End date'), end);
    await user.type(screen.getByLabelText('Reason'), reason);
    await user.tab();
  };
  return {
    user,
    fill,
    http: TestBed.inject(HttpTestingController),
    submit: () => screen.getByRole('button', { name: 'Submit' }) as HTMLButtonElement,
  };
}

describe('ApplyPage', () => {
  afterEach(() => sessionStorage.clear());

  it('shows the date-range error and keeps Submit disabled (UI-12)', async () => {
    const { fill, submit } = await renderApply();
    await fill('01/13/2027', '01/12/2027');

    expect(await screen.findByText('End date must be on or after the start date')).toBeTruthy();
    expect(submit().disabled).toBe(true);
  });

  it('sends the request with an Idempotency-Key (UI-14)', async () => {
    const { user, fill, http, submit } = await renderApply();
    await fill('01/12/2027', '01/12/2027');
    await user.click(submit());

    const req = http.expectOne('/api/leave-requests');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    expect(req.request.body).toEqual({
      leave_type: 'ANNUAL',
      start_date: '2027-01-12',
      end_date: '2027-01-12',
      half_day: false,
      reason: 'Family trip',
    });
  });

  it('requires a reason of at least 10 characters, like the API', async () => {
    const { fill, submit } = await renderApply();
    await fill('01/12/2027', '01/12/2027', 'Trip');

    expect(await screen.findByText('Reason must be at least 10 characters')).toBeTruthy();
    expect(submit().disabled).toBe(true);
  });

  it('shows a 422 field error under the matching field', async () => {
    const { user, fill, http, submit } = await renderApply();
    await fill('01/12/2027', '01/12/2027');
    await user.click(submit());

    http.expectOne('/api/leave-requests').flush(
      {
        error: {
          code: 'VALIDATION_ERROR',
          message: 'The request is invalid.',
          details: [{ field: 'reason', message: 'String should have at least 10 characters' }],
        },
      },
      { status: 422, statusText: 'Unprocessable Entity' },
    );

    expect(await screen.findByText('String should have at least 10 characters')).toBeTruthy();
    expect(screen.getByText('Please correct the highlighted fields.')).toBeTruthy();
  });

  it('shows the 409 overlap message inline and keeps the input (UI-15)', async () => {
    const { user, fill, http, submit } = await renderApply();
    await fill('01/12/2027', '01/13/2027');
    await user.click(submit());

    http.expectOne('/api/leave-requests').flush(
      {
        error: {
          code: 'OVERLAPPING_LEAVE',
          message: 'You already have leave between 2027-01-12 and 2027-01-13.',
        },
      },
      { status: 409, statusText: 'Conflict' },
    );

    expect((await screen.findByRole('alert')).textContent).toContain('You already have leave');
    expect((screen.getByLabelText('Reason') as HTMLTextAreaElement).value).toBe('Family trip');
  });
});
