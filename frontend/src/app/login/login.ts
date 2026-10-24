import { Component, signal, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth';
import { CompanionComponent, Mood } from '../companion/companion';

@Component({
  selector: 'app-login',
  imports: [CompanionComponent],
  templateUrl: './login.html',
  styleUrl: './login.css'
})
export class LoginComponent {
  private auth   = inject(AuthService);
  private router = inject(Router);

  password  = signal('');
  isLoading = signal(false);
  error     = signal('');
  focused   = signal(false);
  success   = signal(false);

  // Covers its eyes while you type the password; peeks again on blur
  mood = computed<Mood>(() => {
    if (this.success()) return 'happy';
    if (this.error()) return 'sad';
    if (this.isLoading()) return 'thinking';
    if (this.focused()) return 'shy';
    return 'idle';
  });

  onInput(e: Event) {
    this.password.set((e.target as HTMLInputElement).value);
    if (this.error()) this.error.set('');
  }

  login() {
    const pwd = this.password().trim();
    if (!pwd || this.isLoading()) return;

    this.isLoading.set(true);
    this.error.set('');

    this.auth.login(pwd).subscribe({
      next: (res) => {
        this.auth.saveToken(res.token);
        this.success.set(true);
        setTimeout(() => this.router.navigate(['/dashboard']), 700);
      },
      error: () => {
        this.error.set('That’s not it. Try again?');
        this.isLoading.set(false);
        this.password.set('');
      }
    });
  }

  onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') this.login();
  }
}
