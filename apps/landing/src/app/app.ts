import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SiteNav } from './features/landing/sections/site-nav';
import { SiteFooter } from './features/landing/sections/site-footer';

/**
 * App shell — the nav, footer, and brand background wrap every route so the
 * catalog pages share the marketing chrome. Route content renders in the outlet.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, SiteNav, SiteFooter],
  template: `
    <div class="vx-atmosphere"></div>
    <div class="vx-grid"></div>
    <div class="vx-stars" aria-hidden="true"><i></i><i></i></div>
    <div class="page">
      <vx-site-nav />
      <router-outlet />
      <vx-site-footer />
    </div>
  `,
})
export class App {}
