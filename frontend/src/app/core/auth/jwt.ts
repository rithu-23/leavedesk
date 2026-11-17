import { JwtClaims } from '../api.types';

/**
 * Reads the payload (middle part) of a JWT without checking its signature.
 * The browser can't check the signature (it doesn't have the secret) and doesn't need to:
 * the API checks it on every request. The UI only uses the claims to decide what to show.
 * Returns null for anything that isn't a LeaveDesk token.
 */
export function decodeJwt(token: string): JwtClaims | null {
  const parts = token.split('.');
  if (parts.length !== 3) {
    return null;
  }
  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const claims = JSON.parse(atob(padded)) as Partial<JwtClaims>;
    if (
      typeof claims.sub === 'string' &&
      (claims.role === 'employee' || claims.role === 'manager') &&
      typeof claims.exp === 'number'
    ) {
      return { sub: claims.sub, role: claims.role, exp: claims.exp };
    }
    return null;
  } catch {
    return null;
  }
}
