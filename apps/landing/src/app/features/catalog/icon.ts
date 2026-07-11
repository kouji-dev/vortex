import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Inline line icons (stroke=currentColor). Names match capability keys + nav. */
@Component({
  selector: 'vx-icon',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      @switch (name()) {
        @case ('tools') {
          <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2-2 2.5-2.5Z" />
        }
        @case ('vision') {
          <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" /><circle cx="12" cy="12" r="2.5" />
        }
        @case ('reasoning') {
          <path d="M12 3l1.9 4.1L18 9l-4.1 1.9L12 15l-1.9-4.1L6 9l4.1-1.9L12 3Z" />
          <path d="M18 15l.7 1.6 1.6.7-1.6.7-.7 1.6-.7-1.6-1.6-.7 1.6-.7.7-1.6Z" />
        }
        @case ('streaming') { <path d="M3 12h4l2-6 4 12 2-6h6" /> }
        @case ('jsonSchema') {
          <path d="M8 4C6 4 6 6 6 8s0 4-2 4c2 0 2 2 2 4s0 4 2 4" />
          <path d="M16 4c2 0 2 2 2 4s0 4 2 4c-2 0-2 2-2 4s0 4-2 4" />
        }
        @case ('caching') {
          <ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
          <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
        }
        @case ('webSearch') {
          <circle cx="12" cy="12" r="9" /><path d="M3 12h18" />
          <path d="M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
        }
        @case ('search') { <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /> }
        @case ('back') { <path d="m15 18-6-6 6-6" /> }
      }
    </svg>
  `,
  styles: [
    ':host{display:inline-block;width:1em;height:1em;line-height:0}svg{display:block;width:100%;height:100%}',
  ],
})
export class Icon {
  readonly name = input.required<string>();
}
