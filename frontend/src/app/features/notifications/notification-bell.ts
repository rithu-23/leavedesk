import { A11yModule } from '@angular/cdk/a11y';
import { CdkConnectedOverlay, CdkOverlayOrigin, ConnectedPosition } from '@angular/cdk/overlay';
import { DatePipe } from '@angular/common';
import { Component, effect, inject, signal, untracked } from '@angular/core';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';

import { NotificationsStore } from './notifications.store';

/**
 * Toolbar bell (UI_SPEC.md §5.5, §8).
 * - The badge shows store.unreadCount() and is hidden at 0.
 * - The button's accessible name includes the count, and a hidden live region announces
 *   changes, so screen-reader users hear new notifications.
 * - The panel is a small popup anchored to the bell (CDK overlay) with role="dialog":
 *   focus moves into it, Escape or a click outside closes it, and focus returns to the bell.
 *   (A Material menu would announce a list of commands, which a notification list is not.)
 * - Opening the panel marks everything read through the API.
 * - Each live notification pops up as a snackbar with a View action that opens the panel.
 */
@Component({
  selector: 'app-notification-bell',
  imports: [
    A11yModule,
    CdkConnectedOverlay,
    CdkOverlayOrigin,
    DatePipe,
    MatBadgeModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './notification-bell.html',
  styleUrl: './notification-bell.scss',
})
export class NotificationBell {
  protected readonly store = inject(NotificationsStore);
  private readonly snackBar = inject(MatSnackBar);

  protected readonly open = signal(false);

  /** Below the bell, right edges aligned; above it if there is no room below. */
  protected readonly positions: ConnectedPosition[] = [
    { originX: 'end', originY: 'bottom', overlayX: 'end', overlayY: 'top', offsetY: 4 },
    { originX: 'end', originY: 'top', overlayX: 'end', overlayY: 'bottom', offsetY: -4 },
  ];

  constructor() {
    effect(() => {
      const latest = this.store.latest();
      if (latest) {
        untracked(() => {
          this.snackBar
            .open(latest.message, 'View', { duration: 5000 })
            .onAction()
            .subscribe(() => this.show());
        });
      }
    });
  }

  protected toggle(): void {
    if (this.open()) {
      this.close();
    } else {
      this.show();
    }
  }

  protected show(): void {
    this.open.set(true);
    this.store.markAllRead();
  }

  protected close(): void {
    this.open.set(false);
  }
}
