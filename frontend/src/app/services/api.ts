import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { AuthService } from './auth';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private auth = inject(AuthService);

  private get authHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Authorization': `Bearer ${this.auth.getToken()}`
    });
  }

  // ── Chat ──────────────────────────────────────────────────────────────────
  askSimple(query: string, history: any[]) {
    return this.http.post<any>(`${environment.apiUrl}/ask-simple`, { query, history });
  }

  // ── JD Match ──────────────────────────────────────────────────────────────
  jdMatch(jd_text: string) {
    return this.http.post<any>(`${environment.apiUrl}/jd-match`, { jd_text });
  }

  // ── Dashboard (protected) ─────────────────────────────────────────────────
  getStats() {
    return this.http.get<any>(`${environment.apiUrl}/dashboard/stats`, {
      headers: this.authHeaders
    });
  }

  getGaps() {
    return this.http.get<any>(`${environment.apiUrl}/dashboard/gaps`, {
      headers: this.authHeaders
    });
  }

  answerGap(gap_id: string, answer: string) {
    return this.http.post<any>(`${environment.apiUrl}/dashboard/answer`,
      { gap_id, answer },
      { headers: this.authHeaders }
    );
  }

  dismissGap(gap_id: string) {
    return this.http.delete<any>(`${environment.apiUrl}/dashboard/gaps/${gap_id}`, {
      headers: this.authHeaders
    });
  }
}