"""
rag.py — RAG Engine
=====================
Core retrieval-augmented generation logic.

Handles:
  - Semantic retrieval from ChromaDB
  - Streaming answer generation via Groq
  - Non-streaming answer generation
  - JD matching feature
  - Confidence gating (threshold: 0.45)
  - Conversation history injection

Loaded once at module import — shared across all FastAPI requests.
"""

import os
import chromadb
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv
from typing import Generator

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH          = "chroma_db"
COLLECTION_NAME      = "harsh_knowledge"
CONFIDENCE_THRESHOLD = 0.45   # below this → "I don't know"
TOP_K                = 4      # number of chunks to retrieve per query
MODEL_NAME           = "llama-3.1-8b-instant"
MAX_HISTORY_TURNS    = 3      # how many past exchanges to inject (3 = last 3 Q&A pairs)


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a professional AI assistant representing Harsh Jaiswal.

Your job is to answer questions about Harsh accurately and confidently, using ONLY the context provided below.

Rules:
1. Write in third person: "Harsh has...", "He built...", "His GPA is..."
2. Be concise and professional. Recruiters are busy — give direct, specific answers.
3. Always ground your answer in the context. Do not add information not present.
4. At the very end of your answer, always add exactly one line:
   SOURCES: [comma-separated list of source filenames from the metadata]
5. If you cannot find the answer in the context, respond with exactly: I_DONT_KNOW

Do not apologise. Do not say "based on the context". Just answer directly and confidently."""


# ── Module-level singletons (loaded once at startup) ─────────────────────────
print("RAG: Loading embedding model...")
_model = SentenceTransformer("all-MiniLM-L6-v2")
print("RAG: Connecting to ChromaDB...")
_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection = _client.get_collection(COLLECTION_NAME)
print("RAG: Connecting to Groq...")

key = os.getenv("GROQ_API_KEY")

print("Loaded key:", key[:10] + "..." if key else "None")

_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
print("RAG: Ready.")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _cosine_score(distance: float) -> float:
    """
    ChromaDB returns L2 distance by default when using cosine metadata.
    Convert to a 0–1 similarity score: score = 1 / (1 + distance).
    Higher is better.
    """
    return round(1 / (1 + distance), 4)


def retrieve(query: str) -> tuple[list[str], list[float], list[dict]]:
    """
    Embed the query and retrieve the top-K most similar chunks from ChromaDB.

    Returns:
        docs    — list of chunk text strings
        scores  — list of similarity scores (0–1, higher = more relevant)
        metas   — list of metadata dicts (source filename, chunk index)
    """
    query_embedding = _model.encode([query]).tolist()[0]
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=TOP_K,
        include=["documents", "distances", "metadatas"],
    )
    docs   = results["documents"][0]
    dists  = results["distances"][0]
    metas  = results["metadatas"][0]
    scores = [_cosine_score(d) for d in dists]
    return docs, scores, metas


def _build_messages(context: str, query: str, history: list[dict]) -> list[dict]:
    """
    Build the messages array for the Groq API call.
    Injects the last N conversation turns for multi-turn context.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject last MAX_HISTORY_TURNS exchanges (each exchange = user + assistant)
    recent_history = history[-(MAX_HISTORY_TURNS * 2):]
    for turn in recent_history:
        role    = "user" if turn.get("role") == "user" else "assistant"
        content = turn.get("content", "")
        if content:
            messages.append({"role": role, "content": content})

    # Final user message: context + current question
    user_content = f"Context:\n{context}\n\nQuestion: {query}"
    messages.append({"role": "user", "content": user_content})
    return messages


# ── Public API ────────────────────────────────────────────────────────────────
def answer(query: str, history: list[dict] = []) -> dict:
    """
    Non-streaming answer. Returns a dict with answer text, confidence, and sources.

    Returns:
        {
            "answer":    str | None,   # None if not confident
            "confident": bool,
            "score":     float,        # best retrieval score (0–1)
            "sources":   list[str],    # source filenames used
        }
    """
    docs, scores, metas = retrieve(query)
    best_score = max(scores) if scores else 0.0

    # Confidence gate — refuse to answer if retrieval is weak
    if best_score < CONFIDENCE_THRESHOLD:
        return {
            "answer":    None,
            "confident": False,
            "score":     best_score,
            "sources":   [],
        }

    context  = "\n\n---\n\n".join(docs)
    sources  = list(dict.fromkeys(m["source"] for m in metas))  # deduplicated, ordered
    messages = _build_messages(context, query, history)

    response = _groq.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.3,
        max_tokens=400,
    )
    raw = response.choices[0].message.content.strip()

    if "I_DONT_KNOW" in raw:
        return {"answer": None, "confident": False, "score": best_score, "sources": []}

    return {
        "answer":    raw,
        "confident": True,
        "score":     best_score,
        "sources":   sources,
    }


def answer_stream(query: str, history: list[dict] = []) -> Generator[dict, None, None]:
    """
    Streaming answer generator. Yields event dicts consumed by FastAPI's StreamingResponse.

    Event types:
        {"type": "no_answer", "score": float}           — below confidence threshold
        {"type": "token",     "token": str, "score": float}  — each streamed token
        {"type": "done",      "sources": list, "score": float} — stream complete
    """
    docs, scores, metas = retrieve(query)
    best_score = max(scores) if scores else 0.0

    # Confidence gate
    if best_score < CONFIDENCE_THRESHOLD:
        yield {"type": "no_answer", "score": best_score}
        return

    context  = "\n\n---\n\n".join(docs)
    sources  = list(dict.fromkeys(m["source"] for m in metas))
    messages = _build_messages(context, query, history)

    stream = _groq.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.3,
        max_tokens=400,
        stream=True,
    )

    for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            yield {"type": "token", "token": token, "score": best_score}

    yield {"type": "done", "sources": sources, "score": best_score}


def jd_match(jd_text: str) -> dict:
    """
    Job Description matching. Extracts requirements from the JD, retrieves
    relevant profile chunks, and asks Groq to produce a MATCH/PARTIAL/GAP analysis.

    Returns:
        {
            "requirements": str,   # extracted JD requirements (numbered list)
            "analysis":     str,   # MATCH/PARTIAL/GAP analysis with evidence
            "score":        float, # best retrieval confidence
            "sources":      list[str],
        }
    """
    # Step 1: Extract top requirements from JD
    req_response = _groq.chat.completions.create(
        model=MODEL_NAME,
        messages=[{
            "role": "user",
            "content": (
                "Extract the top 5 most important technical requirements from this job description. "
                "Return them as a numbered list. Be specific — include tech names, years of experience, "
                "and seniority where mentioned.\n\n"
                f"Job Description:\n{jd_text}"
            )
        }],
        temperature=0.1,
        max_tokens=250,
    )
    requirements = req_response.choices[0].message.content.strip()

    # Step 2: Retrieve relevant profile chunks using the JD text
    docs, scores, metas = retrieve(jd_text[:600])   # use first 600 chars for embedding
    best_score = max(scores) if scores else 0.0
    context    = "\n\n---\n\n".join(docs)
    sources    = list(dict.fromkeys(m["source"] for m in metas))

    # Step 3: Generate MATCH/PARTIAL/GAP analysis
    analysis_response = _groq.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are evaluating a candidate's fit for a job. "
                    "For each requirement, classify as MATCH, PARTIAL MATCH, or GAP. "
                    "After each classification, add specific evidence from the candidate profile. "
                    "End with a final line: Overall Match: X% — [one-line summary]. "
                    "Be honest and specific."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Candidate Profile:\n{context}\n\n"
                    f"Job Requirements:\n{requirements}\n\n"
                    "Assess the candidate's fit for each requirement with evidence."
                )
            }
        ],
        temperature=0.2,
        max_tokens=700,
    )
    analysis = analysis_response.choices[0].message.content.strip()

    return {
        "requirements": requirements,
        "analysis":     analysis,
        "score":        round(best_score, 4),
        "sources":      sources,
    }