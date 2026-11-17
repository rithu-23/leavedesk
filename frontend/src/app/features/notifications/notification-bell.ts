import { DatePipe } from '@angular/common';
import { Component, effect, inject, untracked, viewChild } from '@angular/core';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule, MatMenuTrigger } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';

import { NotificationsStore } from './notifications.store';

/**
 * Toolbar bell (UI_SPEC.md §5.5, §8).
 * - The badge shows store.unreadCount() and is hidden at 0.
 * - The button's accessible name includes the count, and a hidden live region announces
 *   changes, so screen-reader users hear new notifications.
 * - Opening the panel marks everything read through the API.
 * - Each live notification pops up as a snackbar with a View action that opens the panel.
 */
@Component({
  selector: 'app-notification-bell',
  imports: [
    DatePipe,
    MatBadgeModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './notification-bell.html',
  styleUrl: './notification-bell.scss',
})
export class NotificationBell {
  protected readonly store = inject(NotificationsStore);
  private readonly snackBar = inject(MatSnackBar);
  private readonly trigger = viewChild.required(MatMenuTrigger);

  constructor() {
    effect(() => {
      const latest = this.store.latest();
      if (latest) {
        untracked(() => {
          this.snackBar
            .open(latest.message, 'View', { duration: 5000 })
            .onAction()
            .subscribe(() => this.trigger().openMenu());
        });
      }
    });
  }

  protected onOpened(): void {
    this.store.markAllRead();
  }
}
