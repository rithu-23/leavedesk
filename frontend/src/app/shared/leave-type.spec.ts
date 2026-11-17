import { LEAVE_TYPES, leaveTypeLabel } from './leave-type';

describe('leave type labels', () => {
  it('has a distinct label for every leave type', () => {
    expect(LEAVE_TYPES.map(leaveTypeLabel)).toEqual(['Annual', 'Sick', 'Casual']);
  });

  it('shows an unknown code as-is instead of mislabelling it', () => {
    expect(leaveTypeLabel('PARENTAL')).toBe('PARENTAL');
  });
});
