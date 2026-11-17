import { Component, input } from '@angular/core';

import { LeaveStatus } from '../core/api.types';

/**
 * Shows a leave status as a coloured label. The text is always visible, so the meaning
 * never depends on colour alone (UI_SPEC.md §8).
 */
@Component({
  selector: 'app-status-chip',
  template: `<span class="chip" [class]="status()">{{ status() }}</span>`,
  styles: `
    .chip {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 12px;
      font: var(--mat-sys-label-medium);
      text-transform: capitalize;
      background: var(--mat-sys-surface-container-high);
    }
    .pending {
      background: var(--mat-sys-tertiary-container);
      color: var(--mat-sys-on-tertiary-container);
    }
    .approved {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
    }
    .rejected {
      background: var(--mat-sys-error-container);
      color: var(--mat-sys-on-error-container);
    }
  `,
})
export class StatusChip {
  readonly status = input.required<LeaveStatus>();
}
