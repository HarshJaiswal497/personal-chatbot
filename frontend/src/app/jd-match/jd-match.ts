import { Component, signal, inject } from '@angular/core';
import { ApiService } from '../services/api';

@Component({
  selector: 'app-jd-match',
  imports: [],
  templateUrl: './jd-match.html',
  styleUrl: './jd-match.css'
})
export class JdMatchComponent {
  private api = inject(ApiService);

  jdText    = signal('');
  isLoading = signal(false);
  result    = signal<any>(null);
  error     = signal('');

  onInput(event: Event) {
    this.jdText.set((event.target as HTMLTextAreaElement).value);
  }

  analyze() {
    const text = this.jdText().trim();
    if (!text || text.length < 50 || this.isLoading()) return;

    this.isLoading.set(true);
    this.result.set(null);
    this.error.set('');

    this.api.jdMatch(text).subscribe({
      next:  (res) => { this.result.set(res);  this.isLoading.set(false); },
      error: ()    => { this.error.set('Analysis failed. Make sure the backend is running.'); this.isLoading.set(false); }
    });
  }

  clear() {
    this.jdText.set('');
    this.result.set(null);
    this.error.set('');
  }

  getMatchLines(): { text: string; type: 'match' | 'partial' | 'gap' | 'overall' | 'plain' }[] {
    const analysis = this.result()?.analysis;
    if (!analysis) return [];
    return analysis.split('\n')
      .filter((line: string) => line.trim())
      .map((line: string) => {
        const u = line.toUpperCase();
        if (u.includes('OVERALL'))       return { text: line, type: 'overall' as const };
        if (u.includes('GAP'))           return { text: line, type: 'gap'     as const };
        if (u.includes('PARTIAL MATCH')) return { text: line, type: 'partial' as const };
        if (u.includes('MATCH'))         return { text: line, type: 'match'   as const };
        return { text: line, type: 'plain' as const };
      });
  }

  get overallLine(): string {
    return this.getMatchLines().find(l => l.type === 'overall')?.text ?? '';
  }

  get matchCount():   number { return this.getMatchLines().filter(l => l.type === 'match').length;   }
  get partialCount(): number { return this.getMatchLines().filter(l => l.type === 'partial').length; }
  get gapCount():     number { return this.getMatchLines().filter(l => l.type === 'gap').length;     }
}