"""
main.py — FastAPI Application
================================
All HTTP endpoints for the Personal AI Chatbot.

Endpoints:
  GET  /                    health check
  POST /ask                 streaming chat (SSE)
  POST /ask-simple          non-streaming chat (JSON)
  POST /jd-match            job description analysis
  POST /login               dashboard authentication
  GET  /dashboard/stats     analytics (protected)
  GET  /dashboard/gaps      unanswered questions (protected)
  POST /dashboard/answer    answer a gap question (protected)
  DELETE /dashboard/gaps/{id}  dismiss a gap (protected)

Run with:
  uvicorn main:app --reload
"""

import json
import os
import threading
import uuid
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import rag
import analytics
from auth import create_token, verify_password, verify_token

# ── App setup ─────────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="Harsh Jaiswal — Personal AI Chatbot API",
    description="RAG-powered chatbot representing Harsh Jaiswal professionally.",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow Angular dev server and production domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",       # Angular dev server
        "http://localhost:3000",       # alternative local
        "https://harsh-chatbot.vercel.app",  # production (update when deployed)
        "*",                           # remove this in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Gap question storage ───────────────────────────────────────────────────────
GAP_FILE = "gap_questions.json"


def _load_gaps() -> list:
    if not os.path.exists(GAP_FILE):
        return []
    try:
        return json.load(open(GAP_FILE, encoding="utf-8"))
    except Exception:
        return []


def _save_gaps(gaps: list) -> None:
    with open(GAP_FILE, "w", encoding="utf-8") as f:
        json.dump(gaps, f, indent=2, ensure_ascii=False)


def _add_gap(question: str) -> None:
    """Record an unanswered question so the dashboard can show it."""
    gaps = _load_gaps()
    # Deduplicate — don't add if very similar question already pending
    existing = [g["question"].lower().strip() for g in gaps]
    if question.lower().strip() not in existing:
        gaps.append({
            "id":        str(uuid.uuid4()),
            "question":  question,
            "timestamp": datetime.now().isoformat(),
            "status":    "pending",
        })
        _save_gaps(gaps)


# ── Pydantic models ────────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    query:   str
    history: list[dict] = []   # [{"role": "user"|"assistant", "content": str}]

class JDRequest(BaseModel):
    jd_text: str

class LoginRequest(BaseModel):
    password: str

class AnswerGapRequest(BaseModel):
    gap_id: str
    answer: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health():
    """Health check — used by Render to confirm the service is alive."""
    return {"status": "ok", "service": "Harsh Jaiswal Personal Chatbot API"}


@app.post("/ask", tags=["Chat"])
@limiter.limit("30/minute")
async def ask_streaming(request: Request, body: AskRequest):
    """
    Streaming chat endpoint — returns Server-Sent Events.

    Each event is a JSON string:
      {"type": "token",     "token": "...", "score": 0.87}
      {"type": "done",      "sources": [...], "score": 0.87}
      {"type": "no_answer", "score": 0.32}

    The Angular frontend consumes this via EventSource or fetch + ReadableStream.
    """
    query   = body.query.strip()
    history = body.history

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    def event_generator():
        answered = False
        score    = 0.0
        sources  = []

        for event in rag.answer_stream(query, history):
            event_type = event.get("type")
            score      = event.get("score", 0.0)

            if event_type == "no_answer":
                # Log and flag as gap
                analytics.log_query(query, answered=False, score=score, sources=[])
                _add_gap(query)
                yield f"data: {json.dumps(event)}\n\n"
                return

            elif event_type == "token":
                answered = True
                yield f"data: {json.dumps(event)}\n\n"

            elif event_type == "done":
                sources = event.get("sources", [])
                analytics.log_query(query, answered=True, score=score, sources=sources)
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables Nginx buffering on Render
        },
    )


@app.post("/ask-simple", tags=["Chat"])
@limiter.limit("30/minute")
async def ask_simple(request: Request, body: AskRequest):
    """
    Non-streaming chat endpoint — returns complete JSON response.
    Useful for testing via /docs or simple integrations.
    """
    query   = body.query.strip()
    history = body.history

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    result = rag.answer(query, history)

    if not result["confident"]:
        analytics.log_query(query, answered=False, score=result["score"], sources=[])
        _add_gap(query)
        return {
            "answered": False,
            "message":  "I don't have specific information about that. This question has been flagged for Harsh to answer.",
            "score":    result["score"],
        }

    analytics.log_query(query, answered=True, score=result["score"], sources=result["sources"])
    return {
        "answered": True,
        "answer":   result["answer"],
        "score":    result["score"],
        "sources":  result["sources"],
    }


@app.post("/jd-match", tags=["JD Matcher"])
@limiter.limit("10/minute")
async def jd_match(request: Request, body: JDRequest):
    """
    Job Description matcher.
    Paste any JD → get requirements extracted + MATCH/PARTIAL/GAP analysis.
    """
    jd_text = body.jd_text.strip()

    if not jd_text or len(jd_text) < 50:
        raise HTTPException(status_code=400, detail="Please provide a full job description (at least 50 characters).")

    result = rag.jd_match(jd_text)
    return result


@app.post("/login", tags=["Auth"])
def login(body: LoginRequest):
    """
    Dashboard login. Returns a JWT on success.
    Store the token in the Angular app and send it as:
        Authorization: Bearer <token>
    on all /dashboard/* requests.
    """
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    token = create_token()
    return {"token": token, "expires_in": "24h"}


@app.get("/dashboard/stats", tags=["Dashboard"])
def dashboard_stats(payload: dict = Depends(verify_token)):
    """Analytics summary — protected. Requires valid JWT."""
    return analytics.get_stats()


@app.get("/dashboard/gaps", tags=["Dashboard"])
def dashboard_gaps(payload: dict = Depends(verify_token)):
    """
    Return all pending gap questions — questions the bot couldn't answer.
    Harsh answers these from the dashboard → bot auto-relearns.
    """
    gaps = _load_gaps()
    pending = [g for g in gaps if g.get("status") == "pending"]
    return {"gaps": pending, "count": len(pending)}


@app.post("/dashboard/answer", tags=["Dashboard"])
def answer_gap(body: AnswerGapRequest, payload: dict = Depends(verify_token)):
    """
    Answer a gap question from the dashboard.

    Flow:
      1. Find the gap by ID
      2. Append Q+A to knowledge/answered_gaps.txt
      3. Mark gap as answered
      4. Trigger background re-ingestion so bot learns immediately
    """
    gaps = _load_gaps()
    gap  = next((g for g in gaps if g["id"] == body.gap_id), None)

    if not gap:
        raise HTTPException(status_code=404, detail="Gap question not found.")

    # Append to answered_gaps knowledge file
    answered_gaps_path = os.path.join("knowledge", "answered_gaps.txt")
    with open(answered_gaps_path, "a", encoding="utf-8") as f:
        f.write(f"\nQ: {gap['question']}\nA: {body.answer}\n")

    # Mark as answered in gaps file
    for g in gaps:
        if g["id"] == body.gap_id:
            g["status"]      = "answered"
            g["answer"]      = body.answer
            g["answered_at"] = datetime.now().isoformat()
    _save_gaps(gaps)

    # Background re-ingest — bot learns without restarting the server
    def reingest():
        try:
            import ingest
            ingest.ingest()
            print(f"[reingest] ✓ Re-ingested after answering: '{gap['question']}'")
        except Exception as e:
            print(f"[reingest] ERROR: {e}")

    threading.Thread(target=reingest, daemon=True).start()

    return {
        "success":  True,
        "message":  "Answer saved. Bot is re-learning in the background.",
        "question": gap["question"],
        "answer":   body.answer,
    }


@app.delete("/dashboard/gaps/{gap_id}", tags=["Dashboard"])
def dismiss_gap(gap_id: str, payload: dict = Depends(verify_token)):
    """Dismiss a gap question without answering it (e.g. irrelevant questions)."""
    gaps = _load_gaps()
    gap  = next((g for g in gaps if g["id"] == gap_id), None)

    if not gap:
        raise HTTPException(status_code=404, detail="Gap question not found.")

    for g in gaps:
        if g["id"] == gap_id:
            g["status"] = "dismissed"
    _save_gaps(gaps)

    return {"success": True, "message": "Gap dismissed."}