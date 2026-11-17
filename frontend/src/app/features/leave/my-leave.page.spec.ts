import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { render, screen } from '@testing-library/angular';

import { MyLeavePage } from './my-leave.page';

describe('MyLeavePage (placeholder)', () => {
  it('shows the API status from GET /api/health', async () => {
    await render(MyLeavePage, {
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);

    http.expectOne('/api/health').flush({ status: 'ok' });

    expect(await screen.findByText('API: ok')).toBeTruthy();
    http.verify();
  });

  it('shows a message when the API is unreachable', async () => {
    await render(MyLeavePage, {
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);

    http.expectOne('/api/health').error(new ProgressEvent('error'));

    expect(await screen.findByText(/API: unreachable/)).toBeTruthy();
  });
});
