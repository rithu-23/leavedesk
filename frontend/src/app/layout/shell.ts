import { Component, computed, effect, inject, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '../core/auth/auth.service';
import { LeaveStore } from '../features/leave/leave.store';
import { NotificationBell } from '../features/notifications/notification-bell';
import { NotificationsStore } from '../features/notifications/notifications.store';

interface NavLink {
  path: string;
  label: string;
}

/**
 * App shell: the toolbar and the area where signed-in pages appear.
 * On wide screens the links sit in the toolbar; below 600 px they move into a menu
 * (UI_SPEC.md §5, §8). The Approvals link appears only for managers (UI-2).
 * The shell is where features meet: when a decision notification arrives live, it tells the
 * leave store to reload, so the employee's table and balance update without a refresh (UI-22).
 */
@Component({
  selector: 'app-shell',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    NotificationBell,
  ],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
})
export class Shell {
  protected readonly auth = inject(AuthService);
  private readonly notifications = inject(NotificationsStore);
  private readonly leave = inject(LeaveStore);

  constructor() {
    effect(() => {
      const latest = this.notifications.latest();
      if (latest && latest.event !== 'submitted') {
        untracked(() => this.leave.refresh());
      }
    });
  }

  protected readonly links = computed<NavLink[]>(() => [
    { path: '/leave', label: 'My leave' },
    { path: '/leave/apply', label: 'Apply' },
    ...(this.auth.isManager() ? [{ path: '/approvals', label: 'Approvals' }] : []),
  ]);

  /** Keyboard users can jump past the toolbar straight to the page content (UI-27). */
  protected skipToMain(event: Event): void {
    event.preventDefault();
    document.getElementById('main')?.focus();
  }

  protected logout(): void {
    this.auth.logout('user');
  }
}
