import { Component, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

import { notBlank } from '../leave/leave.validators';

export interface RejectDialogData {
  summary: string;
}

/**
 * Asks for the reason before rejecting (UI-19). Reject stays disabled until a non-blank
 * reason is typed; the dialog closes with the trimmed reason, or undefined if cancelled.
 * The dialog puts focus on its first field (the reason) when it opens.
 */
@Component({
  selector: 'app-reject-dialog',
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    <h2 mat-dialog-title>Reject request?</h2>
    <mat-dialog-content>
      <p>{{ data.summary }}</p>
      <mat-form-field appearance="outline" class="reason">
        <mat-label>Reason</mat-label>
        <textarea
          matInput
          [formControl]="reason"
          rows="3"
          maxlength="500"
          cdkFocusInitial
        ></textarea>
        @if (reason.touched && reason.invalid) {
          <mat-error>A reason is required</mat-error>
        }
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Keep</button>
      <button mat-flat-button [disabled]="reason.invalid" (click)="confirm()">Reject</button>
    </mat-dialog-actions>
  `,
  styles: `
    .reason {
      width: 100%;
    }
  `,
})
export class RejectDialog {
  protected readonly data = inject<RejectDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<RejectDialog, string>);

  protected readonly reason = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, notBlank, Validators.maxLength(500)],
  });

  protected confirm(): void {
    if (this.reason.valid) {
      this.ref.close(this.reason.value.trim());
    }
  }
}
