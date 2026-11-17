import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, OnInit } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';

import { ApiError } from '../../core/api-error';
import { LeaveRequest } from '../../core/api.types';
import { ConfirmDialog, ConfirmDialogData } from '../../shared/confirm-dialog';
import { leaveTypeLabel, LeaveTypePipe } from '../../shared/leave-type';
import { ApprovalsStore } from './approvals.store';
import { RejectDialog, RejectDialogData } from './reject-dialog';

/**
 * Manager approvals (UI_SPEC.md §5.4). Loaded lazily and only for managers.
 * Approve asks for confirmation; Reject asks for a reason. Both update the list immediately
 * and roll back if the API refuses.
 */
@Component({
  selector: 'app-approvals-page',
  imports: [
    DatePipe,
    DecimalPipe,
    MatTableModule,
    MatButtonModule,
    MatProgressBarModule,
    LeaveTypePipe,
  ],
  templateUrl: './approvals.page.html',
  styleUrl: './approvals.page.scss',
})
export class ApprovalsPage implements OnInit {
  protected readonly store = inject(ApprovalsStore);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);

  protected readonly columns = ['employee', 'dates', 'type', 'days', 'reason', 'actions'];

  ngOnInit(): void {
    this.store.load();
  }

  protected confirmApprove(request: LeaveRequest): void {
    const data: ConfirmDialogData = {
      title: 'Approve request?',
      message: `Approve ${request.days} day(s) of ${leaveTypeLabel(request.leave_type).toLowerCase()} leave for ${request.employee_id} (${request.start_date} to ${request.end_date})?`,
      confirmLabel: 'Approve',
    };
    this.dialog
      .open(ConfirmDialog, { data, width: '420px', maxWidth: '95vw' })
      .afterClosed()
      .subscribe((confirmed) => {
        if (confirmed) {
          this.store.approve(request).subscribe({
            next: () => this.toast(`Approved ${request.employee_id}'s request`),
            error: (err: ApiError) => this.toast(err.message),
          });
        }
      });
  }

  protected openReject(request: LeaveRequest): void {
    const data: RejectDialogData = {
      summary: `${request.employee_id}: ${request.days} day(s) of ${leaveTypeLabel(request.leave_type).toLowerCase()} leave, ${request.start_date} to ${request.end_date}.`,
    };
    this.dialog
      .open<RejectDialog, RejectDialogData, string>(RejectDialog, {
        data,
        width: '420px',
        maxWidth: '95vw',
      })
      .afterClosed()
      .subscribe((reason) => {
        if (reason) {
          this.store.reject(request, reason).subscribe({
            next: () => this.toast(`Rejected ${request.employee_id}'s request`),
            error: (err: ApiError) => this.toast(err.message),
          });
        }
      });
  }

  private toast(message: string): void {
    this.snackBar.open(message, 'OK', { duration: 4000 });
  }
}
