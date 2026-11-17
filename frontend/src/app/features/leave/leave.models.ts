import { LeaveStatus, LeaveType } from '../../core/api.types';

/** One balance row with numbers (the API sends decimal strings). */
export interface Balance {
  leaveType: LeaveType;
  entitlement: number;
  used: number;
  pending: number;
  available: number;
}

/** What the My leave table is currently showing. */
export interface LeaveQuery {
  status: LeaveStatus | 'all';
  pageIndex: number;
  pageSize: number;
}

/** Body of POST /leave-requests. */
export interface NewLeaveRequest {
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason: string;
  half_day: boolean;
}

/** Load status shared by every list: one value instead of several booleans. */
export type LoadStatus = 'idle' | 'loading' | 'success' | 'error';
