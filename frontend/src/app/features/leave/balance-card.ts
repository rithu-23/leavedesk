import { DecimalPipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { LeaveTypePipe } from '../../shared/leave-type';
import { LeaveStore } from './leave.store';

/**
 * Balance card (UI-8): one row per leave type, plus totals derived with computed() signals
 * in the store. It reads the store directly, so it updates whenever the balance reloads.
 */
@Component({
  selector: 'app-balance-card',
  imports: [DecimalPipe, LeaveTypePipe, MatCardModule, MatProgressBarModule, MatButtonModule],
  template: `
    <mat-card appearance="outlined">
      <mat-card-header>
        <mat-card-title><h2>Balance</h2></mat-card-title>
        <mat-card-subtitle>
          {{ store.totalAvailable() | number: '1.0-1' }} days available in total
        </mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        @switch (store.balanceStatus()) {
          @case ('loading') {
            <mat-progress-bar mode="indeterminate" aria-label="Loading balance" />
          }
          @case ('error') {
            <p class="error" role="alert">{{ store.balanceError()?.message }}</p>
            <button mat-stroked-button (click)="store.loadBalance()">Retry</button>
          }
          @default {
            @if (store.balance().length === 0) {
              <p>No balance found</p>
            } @else {
              <table class="balance">
                <caption class="visually-hidden">
                  Leave balance by type
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Type</th>
                    <th scope="col">Entitlement</th>
                    <th scope="col">Used</th>
                    <th scope="col">Pending</th>
                    <th scope="col">Available</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of store.balance(); track row.leaveType) {
                    <tr [attr.data-testid]="'balance-' + row.leaveType">
                      <th scope="row">{{ row.leaveType | leaveType }}</th>
                      <td>{{ row.entitlement | number: '1.0-1' }}</td>
                      <td data-testid="used">{{ row.used | number: '1.0-1' }}</td>
                      <td>{{ row.pending | number: '1.0-1' }}</td>
                      <td data-testid="available" class="available">
                        {{ row.available | number: '1.0-1' }}
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
              @if (store.lowAnnualBalance()) {
                <p class="warning">Less than 2 days of annual leave left.</p>
              }
            }
          }
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    h2 {
      font: var(--mat-sys-title-large);
      margin: 0;
    }
    .balance {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }
    th,
    td {
      text-align: right;
      padding: 6px 4px;
      border-bottom: 1px solid var(--mat-sys-outline-variant);
    }
    th:first-child {
      text-align: left;
    }
    .available {
      font-weight: 600;
    }
    .error {
      color: var(--mat-sys-error);
    }
    .warning {
      color: var(--mat-sys-tertiary);
      margin: 8px 0 0;
    }
  `,
})
export class BalanceCard {
  protected readonly store = inject(LeaveStore);
}
