import { fakeToken } from '../../testing/fake-token';
import { decodeJwt } from './jwt';

describe('decodeJwt', () => {
  it('reads sub, role and exp from a LeaveDesk token', () => {
    const claims = decodeJwt(fakeToken('E-ANA', 'employee'));
    expect(claims?.sub).toBe('E-ANA');
    expect(claims?.role).toBe('employee');
    expect(typeof claims?.exp).toBe('number');
  });

  it('returns null for something that is not a JWT', () => {
    expect(decodeJwt('not-a-token')).toBeNull();
    expect(decodeJwt('a.%%%.c')).toBeNull();
  });

  it('returns null when the role is unknown', () => {
    const payload = btoa(JSON.stringify({ sub: 'X', role: 'admin', exp: 9999999999 }));
    expect(decodeJwt(`h.${payload}.s`)).toBeNull();
  });
});
