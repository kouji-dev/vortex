import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../data/auth-service';

async function currentUser(auth: AuthService) {
  return auth.user() === undefined ? await auth.loadSession() : auth.user();
}

/**
 * Restricts admin-console routes to owners/admins. Members are sent to
 * /overview (their shared home). Runs after authGuard, so a signed-out
 * visitor is already handled — this only gates by role.
 */
export const adminGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  await currentUser(auth);
  return auth.isAdmin() ? true : router.createUrlTree(['/overview']);
};
