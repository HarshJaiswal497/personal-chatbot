"""
auth.py — JWT Authentication
==============================
Handles dashboard login and token verification.

Flow:
  POST /login  →  verify password  →  issue JWT  →  client stores token
  GET  /dashboard/*  →  verify JWT in Authorization header  →  allow/deny
"""

import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
JWT_SECRET          = os.getenv("JWT_SECRET", "fallback_secret_change_in_production")
DASHBOARD_PASSWORD  = os.getenv("DASHBOARD_PASSWORD", "admin123")
JWT_ALGORITHM       = "HS256"
TOKEN_EXPIRE_HOURS  = 24

security = HTTPBearer()


# ── Token creation ─────────────────────────────────────────────────────────────
def create_token() -> str:
    """Issue a JWT valid for TOKEN_EXPIRE_HOURS hours."""
    payload = {
        "sub":  "dashboard_admin",
        "iat":  datetime.now(timezone.utc),
        "exp":  datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── Password verification ──────────────────────────────────────────────────────
def verify_password(password: str) -> bool:
    """Simple constant-time comparison against env password."""
    return password == DASHBOARD_PASSWORD


# ── Token verification (FastAPI dependency) ────────────────────────────────────
def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    FastAPI dependency — inject into any protected route:
        @app.get("/dashboard/something")
        def protected(payload=Depends(verify_token)):
            ...

    Raises HTTP 401 if token is missing, expired, or invalid.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")