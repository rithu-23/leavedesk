import { Role } from '../core/api.types';

function base64Url(value: object): string {
  return btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * Builds a JWT-shaped string for tests. The signature is fake: the UI never checks it.
 * expiresInSeconds can be negative to make an already-expired token.
 */
export function fakeToken(sub: string, role: Role, expiresInSeconds = 1800): string {
  const exp = Math.floor(Date.now() / 1000) + expiresInSeconds;
  return `${base64Url({ alg: 'HS256', typ: 'JWT' })}.${base64Url({ sub, role, exp })}.signature`;
}

/** Empty routes so tests can navigate to /login and /leave without loading real pages. */
export const TEST_ROUTES = [
  { path: 'login', children: [] },
  { path: 'leave', children: [] },
];

/** Signs a test in as this user by putting a token where AuthService looks on startup. */
export function signInAs(sub: string, role: Role): void {
  sessionStorage.setItem('leavedesk.token', fakeToken(sub, role));
}
