import { Component, signal, computed, inject, DestroyRef } from '@angular/core';
import { ApiService } from '../services/api';
import { CompanionComponent, Mood } from '../companion/companion';
import { renderMarkdown, sourceLabel } from '../shared/format';

type Verdict = 'match' | 'partial' | 'gap';

interface Requirement {
  name:     string;
  verdict:  Verdict;
  evidence: string[];
}

interface Analysis {
  items:   Requirement[];
  overall: number | null;   // "Overall Match: X%" from the model
  summary: string;          // sentence after the percentage
  raw:     string;
}

const LOADING_LINES = [
  'Reading the job description…',
  'Pulling out the must-haves…',
  'Cross-checking Harsh’s projects…',
  'Looking for internship evidence…',
  'Weighing it all up…',
];

const SAMPLE_JD = `Full Stack Developer (Java / Angular)

We're looking for a developer to build and scale customer-facing features end to end.

Requirements:
- Strong Java and Spring Boot experience, building REST APIs and microservices
- Frontend experience with Angular or React and TypeScript
- Relational databases (MySQL or PostgreSQL) and JPA/Hibernate
- Docker, CI/CD pipelines, and deployment to AWS or GCP
- Bonus: experience integrating LLMs, RAG, or other AI/ML features into products
- Good communication and comfort working in an agile team`;

@Component({
  selector: 'app-jd-match',
  imports: [CompanionComponent],
  templateUrl: './jd-match.html',
  styleUrl: './jd-match.css'
})
export class JdMatchComponent {
  private api = inject(ApiService);

  jdText    = signal('');
  isLoading = signal(false);
  result    = signal<any>(null);
  error     = signal('');
  filter    = signal<'all' | Verdict>('all');
  loadingLine = signal(LOADING_LINES[0]);

  private loadingTimer?: ReturnType<typeof setInterval>;

  readonly sourceLabel = sourceLabel;
  readonly renderMarkdown = renderMarkdown;

  analysis = computed<Analysis | null>(() => {
    const raw = this.result()?.analysis as string | undefined;
    return raw ? parseAnalysis(raw) : null;
  });

  counts = computed(() => {
    const items = this.analysis()?.items ?? [];
    return {
      match:   items.filter(i => i.verdict === 'match').length,
      partial: items.filter(i => i.verdict === 'partial').length,
      gap:     items.filter(i => i.verdict === 'gap').length,
      total:   items.length,
    };
  });

  /** Headline number: the model's overall %, else share of matched requirements */
  fitPercent = computed(() => {
    const a = this.analysis();
    if (!a) return 0;
    if (a.overall !== null) return a.overall;
    const c = this.counts();
    return c.total ? Math.round(((c.match + c.partial * 0.5) / c.total) * 100) : 0;
  });

  visibleItems = computed(() => {
    const f = this.filter();
    const items = this.analysis()?.items ?? [];
    return f === 'all' ? items : items.filter(i => i.verdict === f);
  });

  mood = computed<Mood>(() => {
    if (this.isLoading()) return 'thinking';
    if (this.error()) return 'sad';
    if (this.analysis()) return this.fitPercent() >= 60 ? 'happy' : 'idle';
    if (this.jdText().trim()) return 'listening';
    return 'idle';
  });

  constructor() {
    inject(DestroyRef).onDestroy(() => clearInterval(this.loadingTimer));
  }

  onInput(event: Event) {
    this.jdText.set((event.target as HTMLTextAreaElement).value);
  }

  useSample() {
    this.jdText.set(SAMPLE_JD);
  }

  analyze() {
    const text = this.jdText().trim();
    if (!text || text.length < 50 || this.isLoading()) return;

    this.isLoading.set(true);
    this.result.set(null);
    this.error.set('');
    this.filter.set('all');
    this._startLoadingLines();

    this.api.jdMatch(text).subscribe({
      next:  (res) => { this.result.set(res); this._stopLoading(); },
      error: ()    => { this.error.set('Analysis failed. Make sure the backend is running.'); this._stopLoading(); }
    });
  }

  clear() {
    this.jdText.set('');
    this.result.set(null);
    this.error.set('');
  }

  /** Ring gauge: circumference of r=52 */
  readonly ringC = 2 * Math.PI * 52;
  ringOffset(pct: number) { return this.ringC * (1 - pct / 100); }

  private _startLoadingLines() {
    let i = 0;
    this.loadingLine.set(LOADING_LINES[0]);
    clearInterval(this.loadingTimer);
    this.loadingTimer = setInterval(() => {
      i = (i + 1) % LOADING_LINES.length;
      this.loadingLine.set(LOADING_LINES[i]);
    }, 1900);
  }

  private _stopLoading() {
    clearInterval(this.loadingTimer);
    this.isLoading.set(false);
  }
}

// ── Parsing the model's free-text analysis ─────────────────────────────

function toVerdict(text: string): Verdict | null {
  const u = text.toUpperCase();
  if (u.includes('PARTIAL')) return 'partial';
  if (u.includes('GAP') || u.includes('NO MATCH') || u.includes('MISSING')) return 'gap';
  if (u.includes('MATCH')) return 'match';
  return null;
}

const clean = (s: string) => s.replace(/\*\*/g, '').replace(/^#+\s*/, '').trim();

function parseAnalysis(raw: string): Analysis {
  const lines = raw.split('\n').map(l => l.trim());
  const items: Requirement[] = [];
  let overall: number | null = null;
  let summary = '';

  // Overall line, wherever it is
  for (const line of lines) {
    const m = clean(line).match(/overall\s*(?:match|fit)?\s*[:\-–]?\s*(\d{1,3})\s*%\s*[—–\-:]*\s*(.*)/i);
    if (m) { overall = Math.min(100, +m[1]); summary = m[2].trim(); }
  }

  // Shape 1: markdown table with Requirement / Classification / Evidence columns
  const tableRows = lines.filter(l => l.startsWith('|'));
  if (tableRows.length >= 3) {
    const cells = (row: string) => row.split('|').slice(1, -1).map(c => clean(c));
    const header = cells(tableRows[0]).map(h => h.toLowerCase());
    const iReq = header.findIndex(h => h.includes('requirement') || h.includes('skill'));
    const iCls = header.findIndex(h => h.includes('class') || h.includes('verdict') || h.includes('status') || h.includes('match'));
    const iEv  = header.findIndex(h => h.includes('evidence'));
    if (iReq >= 0 && iCls >= 0) {
      for (const row of tableRows.slice(1)) {
        if (/^\|[\s:\-|]+\|$/.test(row)) continue;   // separator row
        const c = cells(row);
        const verdict = toVerdict(c[iCls] ?? '');
        if (!verdict || !c[iReq]) continue;
        const ev = iEv >= 0 ? (c[iEv] ?? '').split(/<br\s*\/?>|;\s+/i).map(s => s.trim()).filter(Boolean) : [];
        items.push({ name: c[iReq], verdict, evidence: ev });
      }
    }
  }

  // Shape 2: "Requirement: … / Classification: … / Evidence: …" blocks
  if (!items.length) {
    let cur: Requirement | null = null;
    let inEvidence = false;
    for (const rawLine of lines) {
      const line = clean(rawLine);
      if (!line || /^-{3,}$/.test(line)) continue;
      // "Requirement: Java" or "Requirement 1: Java"
      const req = line.match(/^(?:\d+[.)]\s*)?requirement(?:\s*#?\d+)?\s*[:\-–]\s*(.*)/i);
      const cls = line.match(/^classification\s*[:\-–]\s*(.*)/i);
      const ev  = line.match(/^evidence\s*[:\-–]?\s*(.*)/i);
      // Evidence keeps its markdown (bold tech names) for rendering
      const evText = rawLine.replace(/^\s*[-*•]\s*/, '').trim();
      if (req) {
        if (cur) items.push(cur);
        cur = { name: req[1], verdict: 'gap', evidence: [] };
        inEvidence = false;
      } else if (cls && cur) {
        cur.verdict = toVerdict(cls[1]) ?? cur.verdict;
        inEvidence = false;
      } else if (ev && cur) {
        inEvidence = true;
        if (ev[1]) cur.evidence.push(ev[1].replace(/^[-*•]\s*/, ''));
      } else if (/^overall/i.test(line)) {
        inEvidence = false;
      } else if (cur && inEvidence) {
        cur.evidence.push(evText);
      }
    }
    if (cur) items.push(cur);
  }

  // Shape 3 (fallback): any line mentioning a verdict becomes an item
  if (!items.length) {
    for (const rawLine of lines) {
      const line = clean(rawLine);
      if (!line || /^overall/i.test(line)) continue;
      const verdict = toVerdict(line);
      if (verdict) items.push({ name: line, verdict, evidence: [] });
    }
  }

  return { items, overall, summary, raw };
}
