import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * The Vortex Prism mark — a diamond refracting the pink→violet→blue spectrum
 * with a luminous lavender core. `animated` runs the idle-sway + core-pulse
 * lifecycle motion (marketing brand moment); static instances are used in the
 * nav and footer lockups.
 */
@Component({
  selector: 'vx-prism',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      [attr.viewBox]="'0 0 80 80'"
      [attr.width]="size()"
      [attr.height]="size()"
      aria-label="Vortex Prism"
      style="display:block;"
    >
      <defs>
        <linearGradient [attr.id]="gradId()" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#f472b6" />
          <stop offset="50%" stop-color="#a78bfa" />
          <stop offset="100%" stop-color="#60a5fa" />
        </linearGradient>
      </defs>
      @if (animated()) {
        <g class="vx-prism-box">
          <polygon
            points="40,8 68,40 40,72 12,40"
            fill="none"
            [attr.stroke]="'url(#' + gradId() + ')'"
            stroke-width="2.5"
            stroke-linejoin="round"
          />
          <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" stroke-width="1.5" opacity="0.62" />
          <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" stroke-width="1.5" opacity="0.62" />
          <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" stroke-width="1.5" opacity="0.62" />
          <circle class="vx-prism-core" cx="40" cy="40" r="4" fill="#e0d7ff" />
        </g>
      } @else {
        <polygon
          points="40,8 68,40 40,72 12,40"
          fill="none"
          [attr.stroke]="'url(#' + gradId() + ')'"
          stroke-width="3"
          stroke-linejoin="round"
        />
        @if (rays()) {
          <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" stroke-width="1.5" opacity="0.6" />
          <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" stroke-width="1.5" opacity="0.6" />
          <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" stroke-width="1.5" opacity="0.6" />
        }
        <circle cx="40" cy="40" r="5" fill="#e0d7ff" />
      }
    </svg>
  `,
})
export class Prism {
  readonly size = input(26);
  readonly animated = input(false);
  /** Draw the three refraction rays (static variant only). */
  readonly rays = input(true);
  /** Unique gradient id so multiple prisms on one page don't collide. */
  readonly gradId = input('vxPrism');
}
