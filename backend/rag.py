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
TOP_K                = 8      # number of chunks to retrieve per query
MODEL_NAME           = "llama-3.1-8b-instant"
MAX_HISTORY_TURNS    = 3      # how many past exchanges to inject (3 = last 3 Q&A pairs)


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a professional AI assistant representing Harsh Jaiswal.

Your job is to answer questions about Harsh accurately and confidently using ONLY the provided context.

Rules:

1. Write in third person.
   Example:
   - "Harsh has experience with..."
   - "He developed..."
   - "His GPA is..."

2. Use ONLY information present in the context.

3. When answering technical questions:
   - Mention ALL relevant technologies found in context.
   - Mention project names whenever possible.
   - Mention internship experience if relevant.
   - Mention certifications if relevant.

4. Do not omit technologies that appear in the retrieved context.

5. Prefer concrete facts over vague summaries.

6. If multiple projects are relevant, include all of them.

7. If the answer cannot be found in context, respond exactly:
I_DONT_KNOW

8. At the very end add exactly one line:

9. When answering experience-related questions:

- Include relevant project names.
- Include technologies used.
- Include responsibilities and contributions.
- Include achievements and outcomes.
- Include numbers and metrics whenever available.

Examples:
- Number of APIs built
- Number of pages developed
- Team size
- GPA
- DSA problems solved
- Certifications completed

10. Prefer detailed factual answers over short summaries.

11. If a question is about a skill or technology, explain:
- where Harsh used it
- what he built with it
- his responsibilities
- the outcome

SOURCES: [comma separated filenames]

Do not apologise.
Do not say "based on the context".
Do not invent information.
"""


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
    
    print("\n=== RETRIEVAL DEBUG ===")

    for score, meta in zip(scores, metas):
        print(
            f"{meta['source']} "
            f"(chunk {meta['chunk_index']}) "
            f"score={score}"
        )

    print("=======================\n")
 
    return docs, scores, metas

def retrieve_jd(query: str):
    """
    JD matching retrieval.
    Searches only technical evidence files.
    """

    query_embedding = _model.encode([query]).tolist()[0]

    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=10,
        where={
            "source": {
                "$in": [
                    "jd_evidence.txt",
                    "11_skills.txt",
                    "03_experience_cognizant.txt",
                    "04_project_runway.txt",
                    "05_project_personal_ai_chatbot.txt",
                    "06_project_ai_symptom_diagnosis.txt",
                    "qa_java_springboot.txt",
                    "qa_ai_ml_genai.txt",
                    "qa_cloud_devops.txt"
                ]
            }
        },
        include=["documents", "distances", "metadatas"]
    )

    docs = results["documents"][0]
    dists = results["distances"][0]
    metas = results["metadatas"][0]

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

    context = ""

    for doc, meta in zip(docs, metas):
        source = meta.get("source", "unknown")
        context += f"\n\nSOURCE FILE: {source}\n{doc}"
    
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

    context = ""

    for doc, meta in zip(docs, metas):
        source = meta.get("source", "unknown")
        context += f"\n\nSOURCE FILE: {source}\n{doc}"
    
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
                "Extract ALL technical skills, tools, frameworks, cloud platforms, AI technologies, databases, and programming languages mentioned in the job description."
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
    docs, scores, metas = retrieve_jd(requirements)   # use first 600 chars for embedding
    best_score = max(scores) if scores else 0.0
    context = ""

    for doc, meta in zip(docs, metas):
        source = meta.get("source", "unknown")
        context += f"\n\nSOURCE FILE: {source}\n{doc}"
    
    sources    = list(dict.fromkeys(m["source"] for m in metas))

    # Step 3: Generate MATCH/PARTIAL/GAP analysis
    analysis_response = _groq.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    """
                        You are evaluating Harsh Jaiswal against a job description.

                        Use ONLY the candidate profile provided.

                        For every requirement:

                        MATCH:
                        Candidate has direct hands-on experience with the skill through projects, internship, certifications, coursework, or practical implementation.

                        PARTIAL MATCH:
                        Candidate has indirect exposure, limited experience, or closely related experience.

                        GAP:
                        No evidence exists in the candidate profile.

                        IMPORTANT:
                        Do NOT use years-of-experience requirements when classifying.
                        Classify based on demonstrated skills and evidence only.

                        A fresher candidate can still receive MATCH if strong project or internship evidence exists.

                        Never assume a skill is missing if evidence exists.

                        For each requirement provide:

                        Requirement:
                        Classification:
                        Evidence:

                        Evidence must mention:
                        - project names
                        - internship experience
                        - certifications
                        - technologies

                        End with:

                        Overall Match: X% — one sentence summary.
                    """
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