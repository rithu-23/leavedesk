/**
 * TypeScript shapes of the LeaveDesk API (API_SPEC.md v1.1).
 * Interfaces exist only at compile time: they make the compiler check every field we read.
 */

export type Role = 'employee' | 'manager';
export type LeaveType = 'ANNUAL' | 'SICK';
export type LeaveStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';

/** POST /auth/login response. */
export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
}

/** The claims LeaveDesk puts in the JWT payload. */
export interface JwtClaims {
  sub: string;
  role: Role;
  exp: number;
}

/** The signed-in user as the UI sees it. */
export interface CurrentUser {
  employeeId: string;
  role: Role;
  /** Expiry as milliseconds since 1970 (JavaScript time). */
  expiresAt: number;
}

/** One error shape for every failed API call: {"error": {...}}. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id?: string;
    details?: unknown;
  };
}

/** Paginated list response (GET /leave-requests, GET /notifications). */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  next_cursor?: string | null;
}

/** LeaveRequestOut. */
export interface LeaveRequest {
  id: string;
  employee_id: string;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  half_day: boolean;
  reason: string;
  status: LeaveStatus;
  days: string | number;
  version: number;
  created_at: string;
  decided_by: string | null;
  decision_note: string | null;
}

/** GET /employees/{id}/balance item as it arrives (decimals are strings). */
export interface BalanceDto {
  leave_type: LeaveType;
  entitlement: string;
  used: string;
  pending: string;
  available: string;
}

/** NotificationOut. */
export interface NotificationItem {
  id: string;
  event: string;
  message: string;
  read: boolean;
  created_at: string;
}
