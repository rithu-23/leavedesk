import { provideHttpClient, withFetch } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';

/**
 * Application-wide providers (Angular's dependency-injection setup).
 * - provideRouter: the route table in app.routes.ts; withComponentInputBinding lets
 *   route and query parameters arrive as component inputs.
 * - provideHttpClient: HttpClient for API calls. Step 3 adds the auth interceptor here.
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch()),
  ],
};
