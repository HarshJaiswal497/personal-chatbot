import { Component, signal, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../services/api';

interface Gap {
  id:        string;
  question:  string;
  timestamp: string;
  status:    string;
}

@Component({
  selector: 'app-dashboard',
  imports: [FormsModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class DashboardComponent implements OnInit {
  private api = inject(ApiService);

  stats         = signal<any>(null);
  gaps          = signal<Gap[]>([]);
  isLoading     = signal(true);
  answerInputs  = signal<Record<string, string>>({});
  savingId      = signal<string | null>(null);
  successId     = signal<string | null>(null);

  ngOnInit() {
    this.loadAll();
  }

  loadAll() {
    this.isLoading.set(true);
    this.api.getStats().subscribe({
      next: (s) => this.stats.set(s),
      error: () => {}
    });
    this.api.getGaps().subscribe({
      next: (g) => {
        this.gaps.set(g.gaps ?? []);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });
  }

  setAnswer(gapId: string, value: string) {
    this.answerInputs.update(inputs => ({ ...inputs, [gapId]: value }));
  }

  getAnswer(gapId: string): string {
    return this.answerInputs()[gapId] ?? '';
  }

  saveAnswer(gap: Gap) {
    const answer = this.getAnswer(gap.id).trim();
    if (!answer || this.savingId()) return;

    this.savingId.set(gap.id);
    this.api.answerGap(gap.id, answer).subscribe({
      next: () => {
        this.successId.set(gap.id);
        setTimeout(() => {
          this.gaps.update(gs => gs.filter(g => g.id !== gap.id));
          this.successId.set(null);
          this.savingId.set(null);
          this.loadAll();   // refresh stats
        }, 1500);
      },
      error: () => this.savingId.set(null)
    });
  }

  dismiss(gapId: string) {
    this.api.dismissGap(gapId).subscribe({
      next: () => this.gaps.update(gs => gs.filter(g => g.id !== gapId))
    });
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString('en-IN', {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
    });
  }

  get answerRate(): string {
    const s = this.stats();
    if (!s || s.total_queries === 0) return '0';
    return (s.answer_rate * 100).toFixed(0);
  }
}