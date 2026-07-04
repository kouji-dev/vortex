import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../data/auth-service';

async function currentUser(auth: AuthService) {
  return auth.user() === undefined ? await auth.loadSession() : auth.user();
}

/** Blocks routes for signed-out users; redirects to /login. */
export const authGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const user = await currentUser(auth);
  return user ? true : router.createUrlTree(['/login']);
};

/** Keeps signed-in users out of /login; sends them to the console. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const user = await currentUser(auth);
  return user ? router.createUrlTree(['/']) : true;
};
