import { HttpClient, HttpHeaders } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { map, Observable, tap } from 'rxjs';

import { CurrentUser, TokenResponse } from '../api.types';
import { decodeJwt } from './jwt';

const STORAGE_KEY = 'leavedesk.token';

/**
 * Owns the sign-in state (UI_SPEC.md §5.1, §9).
 * The token lives in a signal and is mirrored to sessionStorage, so a page refresh keeps
 * you signed in but closing the tab signs you out. Everything else (guards, interceptor,
 * toolbar, later the stores) reads the computed signals below.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);

  private readonly tokenSignal = signal<string | null>(null);
  private expiryTimer: ReturnType<typeof setTimeout> | undefined;

  /** The raw JWT, for the interceptor and the SSE URL. */
  readonly token = this.tokenSignal.asReadonly();

  /** Who is signed in, decoded from the token; null when signed out. */
  readonly user = computed<CurrentUser | null>(() => {
    const token = this.tokenSignal();
    const claims = token ? decodeJwt(token) : null;
    return claims
      ? { employeeId: claims.sub, role: claims.role, expiresAt: claims.exp * 1000 }
      : null;
  });

  readonly isLoggedIn = computed(() => this.user() !== null);
  readonly isManager = computed(() => this.user()?.role === 'manager');

  constructor() {
    this.restore();
  }

  /**
   * POST /auth/login as a form (OAuth2 password style). Emits once on success.
   * URLSearchParams encodes every special character. Angular's HttpParams leaves "+"
   * unencoded, and a form decoder reads "+" as a space, so a password with "+" would fail.
   */
  login(email: string, password: string): Observable<void> {
    const body = new URLSearchParams({ username: email, password }).toString();
    const headers = new HttpHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' });
    return this.http.post<TokenResponse>('/api/auth/login', body, { headers }).pipe(
      tap((res) => this.setToken(res.access_token)),
      map(() => undefined),
    );
  }

  /**
   * Signs out: forgets the token and goes to /login.
   * 'expired' is used when the session ended on its own (401 or token expiry).
   */
  logout(reason: 'user' | 'expired' = 'user'): void {
    const returnUrl = this.router.url;
    this.clear();
    if (reason === 'expired') {
      this.snackBar.open('Your session has ended. Please sign in again.', 'OK', {
        duration: 5000,
      });
      const safeReturn = returnUrl.startsWith('/login') ? undefined : returnUrl;
      void this.router.navigate(['/login'], { queryParams: { returnUrl: safeReturn } });
    } else {
      void this.router.navigate(['/login']);
    }
  }

  private setToken(token: string): void {
    const claims = decodeJwt(token);
    if (!claims || claims.exp * 1000 <= Date.now()) {
      this.clear();
      return;
    }
    this.tokenSignal.set(token);
    this.writeStorage(token);
    this.scheduleExpiry(claims.exp * 1000);
  }

  private restore(): void {
    const saved = this.readStorage();
    if (saved) {
      this.setToken(saved);
    }
  }

  private clear(): void {
    clearTimeout(this.expiryTimer);
    this.tokenSignal.set(null);
    this.writeStorage(null);
  }

  private scheduleExpiry(expiresAt: number): void {
    clearTimeout(this.expiryTimer);
    const delay = expiresAt - Date.now();
    // setTimeout can't wait longer than about 24.8 days; tokens last 30 minutes.
    if (delay > 0 && delay < 2_147_000_000) {
      this.expiryTimer = setTimeout(() => this.logout('expired'), delay);
    }
  }

  private readStorage(): string | null {
    try {
      return sessionStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }

  private writeStorage(token: string | null): void {
    try {
      if (token) {
        sessionStorage.setItem(STORAGE_KEY, token);
      } else {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Storage can be unavailable (private mode, blocked cookies); the signal still works.
    }
  }
}
