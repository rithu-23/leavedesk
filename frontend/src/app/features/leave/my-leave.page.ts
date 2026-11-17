import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, OnInit } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../core/api-error';
import { LeaveRequest, LeaveStatus } from '../../core/api.types';
import { ConfirmDialog, ConfirmDialogData } from '../../shared/confirm-dialog';
import { leaveTypeLabel, LeaveTypePipe } from '../../shared/leave-type';
import { StatusChip } from '../../shared/status-chip';
import { BalanceCard } from './balance-card';
import { LeaveStore } from './leave.store';

/**
 * My leave page (UI_SPEC.md §5.2, UI-8 to UI-11): the balance card and a Material table of
 * the user's requests with a status filter and pagination. All data comes from LeaveStore.
 */
@Component({
  selector: 'app-my-leave-page',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatTableModule,
    MatPaginatorModule,
    MatSelectModule,
    MatFormFieldModule,
    MatButtonModule,
    MatProgressBarModule,
    BalanceCard,
    StatusChip,
    LeaveTypePipe,
  ],
  templateUrl: './my-leave.page.html',
  styleUrl: './my-leave.page.scss',
})
export class MyLeavePage implements OnInit {
  protected readonly store = inject(LeaveStore);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);

  protected readonly columns = ['dates', 'type', 'days', 'status', 'reason', 'actions'];
  protected readonly statuses: { value: LeaveStatus | 'all'; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'pending', label: 'Pending' },
    { value: 'approved', label: 'Approved' },
    { value: 'rejected', label: 'Rejected' },
    { value: 'cancelled', label: 'Cancelled' },
  ];

  ngOnInit(): void {
    this.store.refresh();
  }

  protected onStatusChange(status: LeaveStatus | 'all'): void {
    this.store.setStatusFilter(status);
  }

  protected onPage(event: PageEvent): void {
    this.store.setPage(event.pageIndex, event.pageSize);
  }

  protected emptyMessage(): string {
    const status = this.store.query().status;
    return status === 'all' ? 'No leave requests yet' : `No ${status} requests`;
  }

  protected confirmCancel(request: LeaveRequest): void {
    const data: ConfirmDialogData = {
      title: 'Cancel this request?',
      message: `${leaveTypeLabel(request.leave_type)} leave from ${request.start_date} to ${request.end_date} will be cancelled.`,
      confirmLabel: 'Cancel request',
    };
    this.dialog
      .open(ConfirmDialog, { data, width: '400px', maxWidth: '95vw' })
      .afterClosed()
      .subscribe((confirmed) => {
        if (!confirmed) {
          return;
        }
        this.store.cancel(request.id).subscribe({
          next: () => this.snackBar.open('Request cancelled', 'OK', { duration: 3000 }),
          error: (err: unknown) =>
            this.snackBar.open(toApiError(err).message, 'OK', { duration: 5000 }),
        });
      });
  }
}
