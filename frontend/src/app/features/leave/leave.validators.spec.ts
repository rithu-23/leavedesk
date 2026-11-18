import { FormControl, FormGroup } from '@angular/forms';

import { leaveDatesValidator, notBlank, toIsoDate, trimmedLength } from './leave.validators';

function group(start: Date | null, end: Date | null, halfDay = false): FormGroup {
  return new FormGroup(
    {
      startDate: new FormControl(start),
      endDate: new FormControl(end),
      halfDay: new FormControl(halfDay),
    },
    { validators: leaveDatesValidator },
  );
}

describe('leave form validators', () => {
  it('rejects an end date before the start date (UI-12)', () => {
    expect(group(new Date(2027, 0, 12), new Date(2027, 0, 11)).errors).toEqual({
      endBeforeStart: true,
    });
  });

  it('accepts a one-day range and a longer range', () => {
    expect(group(new Date(2027, 0, 12), new Date(2027, 0, 12)).errors).toBeNull();
    expect(group(new Date(2027, 0, 12), new Date(2027, 0, 15)).errors).toBeNull();
  });

  it('allows half day only on a single day (UI-13)', () => {
    expect(group(new Date(2027, 0, 12), new Date(2027, 0, 12), true).errors).toBeNull();
    expect(group(new Date(2027, 0, 12), new Date(2027, 0, 13), true).errors).toEqual({
      halfDayMultiDay: true,
    });
  });

  it('treats a reason of only spaces as blank', () => {
    expect(notBlank(new FormControl('   '))).toEqual({ blank: true });
    expect(notBlank(new FormControl('Trip'))).toBeNull();
  });

  it('formats dates as YYYY-MM-DD in local time', () => {
    expect(toIsoDate(new Date(2027, 0, 5))).toBe('2027-01-05');
  });
});

describe('trimmedLength', () => {
  const rule = trimmedLength(10, 500);

  it('measures the reason after trimming spaces, like the API', () => {
    expect(rule(new FormControl('   trip    '))).toEqual({ tooShort: { min: 10 } });
    expect(rule(new FormControl('Family trip'))).toBeNull();
    expect(rule(new FormControl('x'.repeat(501)))).toEqual({ tooLong: { max: 500 } });
  });

  it('leaves an empty field to the required validator', () => {
    expect(rule(new FormControl(''))).toBeNull();
  });
});
