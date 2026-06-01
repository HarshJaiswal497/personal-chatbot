import { Injectable, signal, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http   = inject(HttpClient);
  private router = inject(Router);

  private _isLoggedIn = signal<boolean>(this._checkToken());

  isLoggedIn = this._isLoggedIn.asReadonly();

  private _checkToken(): boolean {
    const token = localStorage.getItem('hj_token');
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.exp * 1000 > Date.now();
    } catch {
      return false;
    }
  }

  login(password: string) {
    return this.http.post<{ token: string }>(
      `${environment.apiUrl}/login`,
      { password }
    );
  }

  saveToken(token: string) {
    localStorage.setItem('hj_token', token);
    this._isLoggedIn.set(true);
  }

  getToken(): string | null {
    return localStorage.getItem('hj_token');
  }

  logout() {
    localStorage.removeItem('hj_token');
    this._isLoggedIn.set(false);
    this.router.navigate(['/login']);
  }
}