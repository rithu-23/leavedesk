import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

interface NavLink {
  path: string;
  label: string;
}

/**
 * App shell: the toolbar and the area where signed-in pages appear.
 * On wide screens the links sit in the toolbar; below 600 px they move into a menu
 * (UI_SPEC.md §5, §8). Step 3 adds the user's role, Log out and the Approvals link;
 * step 6 adds the notification bell.
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
  protected readonly links: NavLink[] = [{ path: '/leave', label: 'My leave' }];
}
