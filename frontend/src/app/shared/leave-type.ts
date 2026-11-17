import { Pipe, PipeTransform } from '@angular/core';

import { LeaveType } from '../core/api.types';

/**
 * The one place that turns leave-type codes into labels. Because the map is typed as
 * Record<LeaveType, string>, adding a type to LeaveType without a label here is a compile error.
 */
export const LEAVE_TYPE_LABELS: Record<LeaveType, string> = {
  ANNUAL: 'Annual',
  SICK: 'Sick',
  CASUAL: 'Casual',
};

/** Leave types in display order (balance rows, form options). */
export const LEAVE_TYPES: LeaveType[] = ['ANNUAL', 'SICK', 'CASUAL'];

/** Label for a code; an unknown code from the API is shown as-is instead of being mislabelled. */
export function leaveTypeLabel(code: string): string {
  return LEAVE_TYPE_LABELS[code as LeaveType] ?? code;
}

/** Template version: {{ request.leave_type | leaveType }} */
@Pipe({ name: 'leaveType' })
export class LeaveTypePipe implements PipeTransform {
  transform(code: string): string {
    return leaveTypeLabel(code);
  }
}
