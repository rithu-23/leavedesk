import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MAT_DATE_LOCALE, provideNativeDateAdapter } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';

import { toApiError } from '../../core/api-error';
import { LeaveType } from '../../core/api.types';
import { LEAVE_TYPES, LeaveTypePipe } from '../../shared/leave-type';
import { leaveDatesValidator, notBlank, toIsoDate } from './leave.validators';
import { LeaveStore } from './leave.store';

/**
 * Apply for leave (UI_SPEC.md §5.3, UI-12 to UI-16).
 * Field rules are Validators on each control; the date-range and half-day rules need two
 * fields, so they are a validator on the whole group. Server errors (409/422) appear inline
 * above the Submit button and the user's input is kept.
 */
@Component({
  selector: 'app-apply-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatCheckboxModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    LeaveTypePipe,
  ],
  // Dates display and are typed as MM/DD/YYYY whatever the browser's language, so the hint
  // under each field is always right. The calendar button works in any case.
  providers: [provideNativeDateAdapter(), { provide: MAT_DATE_LOCALE, useValue: 'en-US' }],
  templateUrl: './apply.page.html',
  styleUrl: './apply.page.scss',
})
export class ApplyPage {
  private readonly store = inject(LeaveStore);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);

  protected readonly form = inject(FormBuilder).group(
    {
      leaveType: ['ANNUAL' as LeaveType, Validators.required],
      startDate: [null as Date | null, Validators.required],
      endDate: [null as Date | null, Validators.required],
      halfDay: [false],
      reason: ['', [Validators.required, notBlank, Validators.maxLength(500)]],
    },
    { validators: leaveDatesValidator },
  );

  protected readonly leaveTypes = LEAVE_TYPES;
  protected readonly submitting = signal(false);
  protected readonly serverError = signal<string | null>(null);

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    this.submitting.set(true);
    this.serverError.set(null);

    // A new key for each press of Submit: a retry of the same press can't create two requests.
    const idempotencyKey = crypto.randomUUID();
    this.store
      .submit(
        {
          leave_type: value.leaveType as LeaveType,
          start_date: toIsoDate(value.startDate as Date),
          end_date: toIsoDate(value.endDate as Date),
          half_day: Boolean(value.halfDay),
          reason: (value.reason ?? '').trim(),
        },
        idempotencyKey,
      )
      .subscribe({
        next: () => {
          this.submitting.set(false);
          this.snackBar.open('Leave request submitted', 'OK', { duration: 3000 });
          void this.router.navigateByUrl('/leave');
        },
        error: (err: unknown) => {
          this.submitting.set(false);
          // 409 OVERLAPPING_LEAVE / INSUFFICIENT_BALANCE and 422 come with a clear message.
          this.serverError.set(toApiError(err).message);
        },
      });
  }
}
