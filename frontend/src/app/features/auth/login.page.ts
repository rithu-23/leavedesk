import { Component, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router } from '@angular/router';

import { toApiError } from '../../core/api-error';
import { AuthService } from '../../core/auth/auth.service';

/** Only same-site paths are allowed as returnUrl, so a link can't send users elsewhere. */
function safeReturnUrl(url: string | undefined): string {
  return url && url.startsWith('/') && !url.startsWith('//') && !url.startsWith('/login')
    ? url
    : '/leave';
}

/**
 * Login page (UI_SPEC.md §5.1, UI-1 to UI-3).
 * A Reactive Form: the form model and its validators live in TypeScript, and the template
 * binds to it with [formGroup] / formControlName.
 */
@Component({
  selector: 'app-login-page',
  imports: [
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './login.page.html',
  styleUrl: './login.page.scss',
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  /** ?returnUrl=… from the address bar (route query params arrive as inputs). */
  readonly returnUrl = input<string>();

  protected readonly form = inject(FormBuilder).nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  protected readonly submitting = signal(false);
  protected readonly error = signal<string | null>(null);

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }
    const { email, password } = this.form.getRawValue();
    this.submitting.set(true);
    this.error.set(null);

    this.auth.login(email.trim(), password).subscribe({
      next: () => {
        this.submitting.set(false);
        void this.router.navigateByUrl(safeReturnUrl(this.returnUrl()));
      },
      error: (err: unknown) => {
        this.submitting.set(false);
        const apiError = toApiError(err);
        // One message for wrong password, unknown email and locked account (UI-3).
        this.error.set(apiError.status === 401 ? 'Invalid email or password.' : apiError.message);
      },
    });
  }
}
