import { Component, signal, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.css'
})
export class LoginComponent {
  private auth   = inject(AuthService);
  private router = inject(Router);

  password  = signal('');
  isLoading = signal(false);
  error     = signal('');

  login() {
    const pwd = this.password().trim();
    if (!pwd || this.isLoading()) return;

    this.isLoading.set(true);
    this.error.set('');

    this.auth.login(pwd).subscribe({
      next: (res) => {
        this.auth.saveToken(res.token);
        this.router.navigate(['/dashboard']);
      },
      error: () => {
        this.error.set('Incorrect password.');
        this.isLoading.set(false);
        this.password.set('');
      }
    });
  }

  onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') this.login();
  }
}