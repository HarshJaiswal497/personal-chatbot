import {
  Component, ElementRef, NgZone, DestroyRef, afterNextRender, computed, inject, input, signal,
} from '@angular/core';

export type Mood =
  | 'idle'       // breathing, blinking, eyes follow the cursor
  | 'listening'  // user is typing: leans in, looks at the composer
  | 'thinking'   // waiting on the backend: looks up, dots orbit
  | 'speaking'   // tokens streaming: mouth moves, bouncy
  | 'happy'      // answer finished: ^ ^ eyes, sparkles
  | 'confused'   // no answer: head tilt, question mark
  | 'shy'        // password field focused: covers its eyes
  | 'sad';       // error

@Component({
  selector: 'app-companion',
  templateUrl: './companion.html',
  styleUrl: './companion.css',
  host: {
    '[attr.data-mood]': 'shownMood()',
    '[class.still]': 'still()',
    '[style.--size.px]': 'size()',
    '[style.--blink-delay.s]': 'blinkDelay',
    'aria-hidden': 'true',
  },
})
export class CompanionComponent {
  mood  = input<Mood>('idle');
  size  = input(160);
  /** Follow the pointer with eyes and a slight body tilt */
  track = input(false);
  /** No ambient animation (used for small inline avatars) */
  still = input(false);

  private poked = signal(false);
  shownMood = computed<Mood>(() => (this.poked() && this.mood() === 'idle' ? 'happy' : this.mood()));

  readonly blinkDelay = +(Math.random() * 3).toFixed(2);

  private host = inject(ElementRef<HTMLElement>);

  constructor() {
    const zone = inject(NgZone);
    const destroyRef = inject(DestroyRef);

    afterNextRender(() => {
      if (!this.track()) return;
      const el = this.host.nativeElement as HTMLElement;
      let frame = 0;

      const onMove = (e: PointerEvent) => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          const r  = el.getBoundingClientRect();
          const dx = e.clientX - (r.left + r.width / 2);
          const dy = e.clientY - (r.top + r.height / 2);
          const dist = Math.hypot(dx, dy) || 1;
          const pull = Math.min(dist / 260, 1);
          el.style.setProperty('--lx', ((dx / dist) * 4.5 * pull).toFixed(2));
          el.style.setProperty('--ly', ((dy / dist) * 4 * pull).toFixed(2));
          el.style.setProperty('--tilt', `${((dx / dist) * 5 * pull).toFixed(2)}deg`);
        });
      };

      zone.runOutsideAngular(() => document.addEventListener('pointermove', onMove, { passive: true }));
      destroyRef.onDestroy(() => {
        document.removeEventListener('pointermove', onMove);
        cancelAnimationFrame(frame);
      });
    });
  }

  poke() {
    if (this.still() || this.poked()) return;
    this.poked.set(true);
    setTimeout(() => this.poked.set(false), 1200);
  }
}
