import { Component, signal, computed, inject, ElementRef, ViewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { StreamService } from '../services/stream';
import { CompanionComponent, Mood } from '../companion/companion';
import { renderMarkdown, sourceLabel } from '../shared/format';

interface Message {
  id:         string;
  role:       'user' | 'assistant';
  content:    string;
  html?:      string;
  score?:     number;
  sources?:   string[];
  error?:     boolean;
  loading?:   boolean;
  streaming?: boolean;
  unknown?:   boolean;
}

const CAPTIONS: Record<Mood, string> = {
  idle:      'Ask me anything. I know a lot about Harsh.',
  listening: 'Ooh, go on, I’m listening…',
  thinking:  'Rummaging through Harsh’s notes…',
  speaking:  'Here’s what I know!',
  happy:     'Hope that helps! Anything else?',
  confused:  'Hmm, that one’s new to me. I’ve passed it to Harsh.',
  shy:       '',
  sad:       'Oops, I can’t reach my brain. Is the backend running?',
};

@Component({
  selector: 'app-chat',
  imports: [CompanionComponent, RouterLink],
  templateUrl: './chat.html',
  styleUrl: './chat.css'
})
export class ChatComponent {
  @ViewChild('scroller') scroller?: ElementRef<HTMLElement>;
  @ViewChild('composer') composer?: ElementRef<HTMLTextAreaElement>;

  private stream = inject(StreamService);

  messages  = signal<Message[]>([]);
  input     = signal('');
  isLoading = signal(false);
  private streamingNow = signal(false);
  private flash        = signal<Mood | null>(null);
  private flashTimer?: ReturnType<typeof setTimeout>;

  mood = computed<Mood>(() => {
    if (this.isLoading()) return this.streamingNow() ? 'speaking' : 'thinking';
    if (this.flash()) return this.flash()!;
    if (this.input().trim()) return 'listening';
    const last = this.messages().at(-1);
    if (last?.error) return 'sad';
    return 'idle';
  });

  caption = computed(() => CAPTIONS[this.mood()]);

  readonly suggestions = [
    { icon: '👋', text: 'Who is Harsh, in a nutshell?',      tone: 'peach'  },
    { icon: '🛠️', text: 'What projects has he built?',      tone: 'lilac'  },
    { icon: '🌱', text: 'How good is he with Spring Boot?',  tone: 'mint'   },
    { icon: '🤖', text: 'What’s his experience with AI/ML?', tone: 'sky'    },
    { icon: '🎓', text: 'Where did he study, and his GPA?',  tone: 'butter' },
    { icon: '✈️', text: 'Is he open to relocating?',         tone: 'rose'   },
  ];

  readonly sourceLabel = sourceLabel;

  onInput(event: Event) {
    const el = event.target as HTMLTextAreaElement;
    this.input.set(el.value);
    this._autosize(el);
  }

  ask(text: string) {
    this.input.set(text);
    this.send();
  }

  async send() {
    const query = this.input().trim();
    if (!query || this.isLoading()) return;

    this._clearFlash();
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: query };
    this.messages.update(msgs => [...msgs, userMsg]);
    this.input.set('');
    // Clear the DOM too: with event coalescing, typing + Enter in one frame never
    // renders the typed value, so the [value] binding sees '' → '' and skips the write.
    if (this.composer) {
      this.composer.nativeElement.value = '';
      this._autosize(this.composer.nativeElement);
    }
    this.isLoading.set(true);
    this.streamingNow.set(false);
    this._scrollToBottom();

    // History for context (last 6 messages = 3 exchanges)
    const history = this.messages()
      .slice(-7, -1)
      .filter(m => !m.loading && !m.error && !m.unknown)
      .map(m => ({ role: m.role, content: m.content }));

    const assistantId = crypto.randomUUID();
    this.messages.update(msgs => [...msgs, { id: assistantId, role: 'assistant', content: '', loading: true }]);

    const patch = (p: Partial<Message>) =>
      this.messages.update(msgs => msgs.map(m => (m.id === assistantId ? { ...m, ...p } : m)));

    let full = '';
    let outcome: 'answered' | 'unknown' | 'error' = 'error';

    try {
      for await (const event of this.stream.streamAsk(query, history)) {
        if (event.type === 'token') {
          full += event.token ?? '';
          this.streamingNow.set(true);
          patch({ content: full, html: renderMarkdown(full), loading: false, streaming: true });
          this._scrollToBottom();
        } else if (event.type === 'done') {
          outcome = 'answered';
          patch({ score: event.score, sources: event.sources, loading: false, streaming: false });
        } else if (event.type === 'no_answer') {
          outcome = 'unknown';
          const text = 'I don’t know that one yet. I’ve flagged it for Harsh, and once he answers, I’ll remember it for next time.';
          patch({ content: text, html: renderMarkdown(text), score: event.score, loading: false, unknown: true });
        } else if (event.type === 'error') {
          outcome = 'error';
          patch({ content: 'Something went wrong on my side. Make sure the backend is running.', error: true, loading: false, streaming: false });
        }
      }
    } catch {
      outcome = 'error';
      patch({ content: 'Connection lost. Please try again.', error: true, loading: false, streaming: false });
    }

    if (outcome === 'answered' && !full) outcome = 'error';
    this.isLoading.set(false);
    this.streamingNow.set(false);
    if (outcome === 'answered') this._setFlash('happy', 2600);
    if (outcome === 'unknown')  this._setFlash('confused', 3600);
    this._scrollToBottom();
    this.composer?.nativeElement.focus();
  }

  onKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  clearChat() {
    this.messages.set([]);
    this._clearFlash();
  }

  /** 0–5 filled dots for the retrieval confidence */
  confidenceDots(score = 0): boolean[] {
    const filled = Math.max(1, Math.min(5, Math.round(((score - 0.3) / 0.45) * 5)));
    return Array.from({ length: 5 }, (_, i) => i < filled);
  }

  confidenceWord(score = 0): string {
    if (score >= 0.6) return 'Strong match';
    if (score >= 0.45) return 'Good match';
    return 'Loose match';
  }

  private _setFlash(mood: Mood, ms: number) {
    this._clearFlash();
    this.flash.set(mood);
    this.flashTimer = setTimeout(() => this.flash.set(null), ms);
  }

  private _clearFlash() {
    clearTimeout(this.flashTimer);
    this.flash.set(null);
  }

  private _autosize(el: HTMLTextAreaElement) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  }

  private _scrollToBottom() {
    requestAnimationFrame(() => {
      const el = this.scroller?.nativeElement;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
  }
}
