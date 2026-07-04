import {
  ApplicationConfig,
  provideZonelessChangeDetection,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideLucideIcons } from '@kouji-ui/components';
import { KJ_BUTTON_DEFAULTS, provideKjButton } from '@kouji-ui/core';

import { routes } from './app.routes';
import { credentialsInterceptor } from './shared/http/credentials-interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([credentialsInterceptor])),
    provideLucideIcons(),
    // register the button vocabulary so kjVariant="secondary" (social buttons) renders
    ...provideKjButton({
      variants: [...KJ_BUTTON_DEFAULTS.variants, 'secondary', 'outline-blue', 'inverse'],
    }),
  ],
};
