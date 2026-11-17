import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

/** Same calendar day, ignoring the time of day. */
function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/**
 * Cross-field rules for the apply form (UI-12, UI-13). It runs on the whole form group, because
 * each rule needs two fields at once:
 * - endBeforeStart: the end date is earlier than the start date;
 * - halfDayMultiDay: "half day" is ticked for a range longer than one day.
 */
export const leaveDatesValidator: ValidatorFn = (
  group: AbstractControl,
): ValidationErrors | null => {
  const start = group.get('startDate')?.value as Date | null;
  const end = group.get('endDate')?.value as Date | null;
  const halfDay = group.get('halfDay')?.value as boolean;
  if (!start || !end) {
    return null;
  }
  if (startOfDay(end) < startOfDay(start)) {
    return { endBeforeStart: true };
  }
  if (halfDay && !sameDay(start, end)) {
    return { halfDayMultiDay: true };
  }
  return null;
};

/** A reason made only of spaces counts as empty. */
export const notBlank: ValidatorFn = (control: AbstractControl): ValidationErrors | null =>
  typeof control.value === 'string' && control.value.trim().length === 0 ? { blank: true } : null;

/** Formats a date as YYYY-MM-DD in local time (toISOString would shift it to UTC). */
export function toIsoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}
