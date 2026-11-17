import { httpResource } from '@angular/common/http';
import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';

interface Health {
  status: string;
}

/**
 * Placeholder for the My leave page (replaced in step 4).
 * For now it proves the /api proxy works: it calls GET /api/health, which the dev server
 * forwards to FastAPI as GET /health. httpResource is Angular's signal-based way to load
 * data: value(), isLoading() and error() are signals the template reads directly.
 */
@Component({
  selector: 'app-my-leave-page',
  imports: [MatCardModule, MatProgressBarModule],
  template: `
    <h1>My leave</h1>
    <mat-card appearance="outlined">
      <mat-card-content>
        @if (health.isLoading()) {
          <mat-progress-bar mode="indeterminate" aria-label="Checking the API" />
        } @else if (health.error()) {
          <p role="status">API: unreachable. Is the backend running on port 8000?</p>
        } @else {
          <p role="status">API: {{ health.value()?.status }}</p>
        }
      </mat-card-content>
    </mat-card>
  `,
})
export class MyLeavePage {
  protected readonly health = httpResource<Health>(() => '/api/health');
}
