import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { MatIconRegistry } from '@angular/material/icon';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';

/**
 * Application-wide providers (Angular's dependency-injection setup).
 * - provideRouter: the route table in app.routes.ts; withComponentInputBinding lets
 *   route and query parameters (such as ?returnUrl=) arrive as component inputs.
 * - provideHttpClient: HttpClient for API calls, with the auth interceptor that adds
 *   the token and handles 401s on every request.
 * - The app initializer makes every <mat-icon> use the Material Symbols font that index.html
 *   loads. Without it, mat-icon asks for the older "Material Icons" font, which isn't loaded,
 *   so icons appear as words ("menu", "notifications").
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
    provideAppInitializer(() => {
      inject(MatIconRegistry).setDefaultFontSetClass('material-symbols-outlined');
    }),
  ],
};
