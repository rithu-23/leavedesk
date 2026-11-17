import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { fakeToken, TEST_ROUTES } from '../../testing/fake-token';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

describe('authInterceptor', () => {
  let http: HttpClient;
  let controller: HttpTestingController;
  let auth: AuthService;
  const token = fakeToken('E-ANA', 'employee');

  beforeEach(() => {
    sessionStorage.setItem('leavedesk.token', token);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter(TEST_ROUTES),
      ],
    });
    http = TestBed.inject(HttpClient);
    controller = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
  });

  afterEach(() => sessionStorage.clear());

  it('adds the Bearer token to API calls (UI-4)', () => {
    http.get('/api/leave-requests').subscribe();
    const req = controller.expectOne('/api/leave-requests');
    expect(req.request.headers.get('Authorization')).toBe(`Bearer ${token}`);
  });

  it('does not add the token to the login call or to non-API URLs', () => {
    http.post('/api/auth/login', {}).subscribe();
    http.get('https://example.com/data').subscribe();
    expect(controller.expectOne('/api/auth/login').request.headers.has('Authorization')).toBe(
      false,
    );
    expect(
      controller.expectOne('https://example.com/data').request.headers.has('Authorization'),
    ).toBe(false);
  });

  it('signs the user out when the API answers 401 (UI-5)', () => {
    const logout = vi.spyOn(auth, 'logout');
    http.get('/api/leave-requests').subscribe({ error: () => undefined });

    controller
      .expectOne('/api/leave-requests')
      .flush(
        { error: { code: 'UNAUTHENTICATED', message: 'Not signed in' } },
        { status: 401, statusText: 'Unauthorized' },
      );

    expect(logout).toHaveBeenCalledWith('expired');
    expect(auth.isLoggedIn()).toBe(false);
  });
});
