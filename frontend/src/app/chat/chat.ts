import { Component, signal, inject, ElementRef, ViewChild, afterNextRender } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { StreamService } from '../services/stream';

interface Message {
  id:       string;
  role:     'user' | 'assistant';
  content:  string;
  score?:   number;
  sources?: string[];
  error?:   boolean;
  loading?: boolean;
}

@Component({
  selector: 'app-chat',
  imports: [FormsModule],
  templateUrl: './chat.html',
  styleUrl: './chat.css'
})
export class ChatComponent {
  @ViewChild('messagesEnd') messagesEnd!: ElementRef;

  private stream = inject(StreamService);

  messages  = signal<Message[]>([]);
  input     = signal('');
  isLoading = signal(false);

  readonly suggestions = [
    "Tell me about yourself",
    "What's your GPA and college?",
    "What projects have you built?",
    "Do you know Spring Boot?",
    "What's your experience with AI/ML?",
    "Are you open to relocate?"
  ];

  setInput(text: string) {
    this.input.set(text);
  }

  async send() {
    const query = this.input().trim();
    if (!query || this.isLoading()) return;

    // Add user message
    const userMsg: Message = {
      id:      crypto.randomUUID(),
      role:    'user',
      content: query,
    };
    this.messages.update(msgs => [...msgs, userMsg]);
    this.input.set('');
    this.isLoading.set(true);
    this._scrollToBottom();

    // Build history for context (last 6 messages = 3 exchanges)
    const history = this.messages()
      .slice(-6)
      .filter(m => !m.loading && !m.error)
      .map(m => ({ role: m.role, content: m.content }));

    // Add placeholder assistant message
    const assistantId = crypto.randomUUID();
    const placeholder: Message = {
      id:      assistantId,
      role:    'assistant',
      content: '',
      loading: true,
    };
    this.messages.update(msgs => [...msgs, placeholder]);

    let fullContent = '';
    let answered    = false;

    try {
      for await (const event of this.stream.streamAsk(query, history)) {

        if (event.type === 'token') {
          answered     = true;
          fullContent += event.token ?? '';
          this.messages.update(msgs =>
            msgs.map(m => m.id === assistantId
              ? { ...m, content: fullContent, loading: false }
              : m
            )
          );
          this._scrollToBottom();
        }

        else if (event.type === 'done') {
          this.messages.update(msgs =>
            msgs.map(m => m.id === assistantId
              ? { ...m, score: event.score, sources: event.sources, loading: false }
              : m
            )
          );
        }

        else if (event.type === 'no_answer') {
          this.messages.update(msgs =>
            msgs.map(m => m.id === assistantId
              ? {
                  ...m,
                  content: "I don't have specific information about that yet. Your question has been flagged — Harsh will answer it and I'll learn from it.",
                  score:   event.score,
                  loading: false,
                }
              : m
            )
          );
        }

        else if (event.type === 'error') {
          this.messages.update(msgs =>
            msgs.map(m => m.id === assistantId
              ? { ...m, content: 'Something went wrong. Make sure the backend is running.', error: true, loading: false }
              : m
            )
          );
        }
      }
    } catch {
      this.messages.update(msgs =>
        msgs.map(m => m.id === assistantId
          ? { ...m, content: 'Connection error. Please try again.', error: true, loading: false }
          : m
        )
      );
    }

    this.isLoading.set(false);
    this._scrollToBottom();
  }

  onKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  clearChat() {
    this.messages.set([]);
  }

  private _scrollToBottom() {
    setTimeout(() => {
      this.messagesEnd?.nativeElement?.scrollIntoView({ behavior: 'smooth' });
    }, 50);
  }
}