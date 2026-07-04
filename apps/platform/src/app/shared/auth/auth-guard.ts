import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { PlatformAuthService } from '../data/platform-auth-service';

async function currentEmail(auth: PlatformAuthService) {
  return auth.email() === undefined ? await auth.loadSession() : auth.email();
}

/** Blocks routes for signed-out / non platform-admin users; → /login. */
export const authGuard: CanActivateFn = async () => {
  const auth = inject(PlatformAuthService);
  const router = inject(Router);
  const email = await currentEmail(auth);
  return email ? true : router.createUrlTree(['/login']);
};

/** Keeps signed-in platform admins out of /login. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(PlatformAuthService);
  const router = inject(Router);
  const email = await currentEmail(auth);
  return email ? router.createUrlTree(['/']) : true;
};
