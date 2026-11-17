import { Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '../core/auth/auth.service';

interface NavLink {
  path: string;
  label: string;
}

/**
 * App shell: the toolbar and the area where signed-in pages appear.
 * On wide screens the links sit in the toolbar; below 600 px they move into a menu
 * (UI_SPEC.md §5, §8). The Approvals link appears only for managers (UI-2).
 * Step 6 adds the notification bell.
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
  ],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
})
export class Shell {
  protected readonly auth = inject(AuthService);

  protected readonly links = computed<NavLink[]>(() => [
    { path: '/leave', label: 'My leave' },
    ...(this.auth.isManager() ? [{ path: '/approvals', label: 'Approvals' }] : []),
  ]);

  protected logout(): void {
    this.auth.logout('user');
  }
}
