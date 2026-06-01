import { Injectable, inject } from '@angular/core';
import { environment } from '../../environments/environment';

export interface StreamEvent {
  type: 'token' | 'done' | 'no_answer' | 'error';
  token?: string;
  score?: number;
  sources?: string[];
}

@Injectable({ providedIn: 'root' })
export class StreamService {

  async *streamAsk(query: string, history: any[]): AsyncGenerator<StreamEvent> {
    try {
      const response = await fetch(`${environment.apiUrl}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, history })
      });

      if (!response.ok) {
        yield { type: 'error' };
        return;
      }

      const reader  = response.body!.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';  // keep incomplete line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.slice(5).trim();
          if (!jsonStr) continue;
          try {
            const event: StreamEvent = JSON.parse(jsonStr);
            yield event;
          } catch {
            // malformed chunk — skip
          }
        }
      }
    } catch (err) {
      yield { type: 'error' };
    }
  }
}