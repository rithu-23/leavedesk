import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { fakeToken, TEST_ROUTES } from '../../testing/fake-token';
import { AuthService } from './auth.service';

function setup(): { auth: AuthService; http: HttpTestingController } {
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(TEST_ROUTES)],
  });
  return { auth: TestBed.inject(AuthService), http: TestBed.inject(HttpTestingController) };
}

describe('AuthService', () => {
  beforeEach(() => sessionStorage.clear());

  it('posts the login form and signs the user in (UI-2)', () => {
    const { auth, http } = setup();
    const token = fakeToken('E-ANA', 'employee');

    auth.login('ana@leavedesk.test', 'a+b&c').subscribe();
    const req = http.expectOne('/api/auth/login');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toBe('username=ana%40leavedesk.test&password=a%2Bb%26c');
    expect(req.request.headers.get('Content-Type')).toBe('application/x-www-form-urlencoded');
    req.flush({ access_token: token, token_type: 'bearer', expires_in: 1800 });

    expect(auth.isLoggedIn()).toBe(true);
    expect(auth.user()?.employeeId).toBe('E-ANA');
    expect(auth.isManager()).toBe(false);
    expect(sessionStorage.getItem('leavedesk.token')).toBe(token);
  });

  it('restores a saved token but discards an expired one', () => {
    sessionStorage.setItem('leavedesk.token', fakeToken('E-MO', 'manager', -60));
    const { auth } = setup();
    expect(auth.isLoggedIn()).toBe(false);
    expect(sessionStorage.getItem('leavedesk.token')).toBeNull();
  });

  it('logout forgets the token (UI-7)', () => {
    sessionStorage.setItem('leavedesk.token', fakeToken('E-MO', 'manager'));
    const { auth } = setup();
    expect(auth.isManager()).toBe(true);

    auth.logout();

    expect(auth.isLoggedIn()).toBe(false);
    expect(sessionStorage.getItem('leavedesk.token')).toBeNull();
  });
});
