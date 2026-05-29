"""
analytics.py — Query Logging & Analytics
==========================================
Logs every query to a JSON file and provides summary stats
for the dashboard.

Log file: chat_logs.json  (auto-created, gitignored)

Each entry:
{
    "id":        "uuid4",
    "timestamp": "2026-01-15T10:23:45.123456",
    "query":     "Does Harsh know Spring Boot?",
    "answered":  true,
    "score":     0.847,
    "sources":   ["qa_pairs.txt"]
}
"""

import json
import uuid
import os
from datetime import datetime

LOG_FILE = "chat_logs.json"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_logs() -> list:
    """Load all logs from file. Returns empty list if file doesn't exist."""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_logs(logs: list) -> None:
    """Persist logs list to file."""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


# ── Public API ────────────────────────────────────────────────────────────────
def log_query(query: str, answered: bool, score: float, sources: list[str]) -> None:
    """
    Append a query event to the log file.
    Called after every /ask and /ask-simple request.
    """
    logs = _load_logs()
    logs.append({
        "id":        str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "query":     query,
        "answered":  answered,
        "score":     round(score, 4),
        "sources":   sources,
    })
    _save_logs(logs)


def get_stats() -> dict:
    """
    Return summary statistics for the dashboard.

    Returns:
        {
            "total_queries":     int,
            "answered":          int,
            "unanswered":        int,
            "answer_rate":       float,   # 0.0 – 1.0
            "avg_score":         float,
            "recent_queries":    list,    # last 10 entries, newest first
        }
    """
    logs = _load_logs()

    if not logs:
        return {
            "total_queries":  0,
            "answered":       0,
            "unanswered":     0,
            "answer_rate":    0.0,
            "avg_score":      0.0,
            "recent_queries": [],
        }

    total      = len(logs)
    answered   = sum(1 for l in logs if l.get("answered"))
    unanswered = total - answered
    avg_score  = round(sum(l.get("score", 0) for l in logs) / total, 4)
    recent     = sorted(logs, key=lambda l: l["timestamp"], reverse=True)[:10]

    return {
        "total_queries":  total,
        "answered":       answered,
        "unanswered":     unanswered,
        "answer_rate":    round(answered / total, 4),
        "avg_score":      avg_score,
        "recent_queries": recent,
    }