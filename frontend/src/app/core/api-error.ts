import { HttpErrorResponse } from '@angular/common/http';

import { ApiErrorBody } from './api.types';

/** A failed API call, reduced to what screens need (UI_SPEC.md §7). */
export interface ApiError {
  /** HTTP status; 0 means the server could not be reached. */
  status: number;
  /** Error code from the API, e.g. OVERLAPPING_LEAVE, or a UI code such as NETWORK. */
  code: string;
  /** Human-readable message to show. */
  message: string;
  requestId?: string;
  details?: unknown;
}

function isApiErrorBody(body: unknown): body is ApiErrorBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    'error' in body &&
    typeof (body as ApiErrorBody).error?.message === 'string'
  );
}

/** One entry of a 422 response's details: which field was wrong and why. */
export interface FieldError {
  field: string;
  message: string;
}

/**
 * Reads the field errors of a 422 VALIDATION_ERROR: details is a list of {field, message}.
 * Anything else gives an empty list, so callers can always loop over the result.
 */
export function fieldErrors(error: ApiError): FieldError[] {
  if (!Array.isArray(error.details)) {
    return [];
  }
  return error.details.filter(
    (d): d is FieldError =>
      typeof d === 'object' &&
      d !== null &&
      typeof (d as FieldError).field === 'string' &&
      typeof (d as FieldError).message === 'string',
  );
}

/** Turns anything thrown by HttpClient into an ApiError. Never throws. */
export function toApiError(err: unknown): ApiError {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) {
      return { status: 0, code: 'NETWORK', message: "Can't reach the server." };
    }
    if (isApiErrorBody(err.error)) {
      const { code, message, request_id, details } = err.error.error;
      if (request_id) {
        console.warn(`LeaveDesk API error ${err.status} ${code} (request ${request_id})`);
      }
      return { status: err.status, code, message, requestId: request_id, details };
    }
    if (err.status === 503) {
      return { status: 503, code: 'UNAVAILABLE', message: 'The server is busy. Please try again.' };
    }
    return { status: err.status, code: 'HTTP_ERROR', message: `Request failed (${err.status}).` };
  }
  return { status: -1, code: 'UNKNOWN', message: 'Something went wrong.' };
}
