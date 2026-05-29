"""
ingest.py — Knowledge Base Ingestion
=====================================
Reads all .txt files from knowledge/, chunks them, embeds with
sentence-transformers, and stores in ChromaDB.

Run this:
  - On first setup
  - After editing any file in knowledge/
  - After answering gap questions from the dashboard (auto-triggered)

Usage:
  python ingest.py
"""

import os
import glob
import chromadb
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────────
KNOWLEDGE_DIR    = "knowledge"
CHROMA_PATH      = "chroma_db"
COLLECTION_NAME  = "harsh_knowledge"
CHUNK_SIZE       = 300   # characters per chunk
CHUNK_OVERLAP    = 50    # overlap between consecutive chunks
MIN_CHUNK_LEN    = 30    # discard chunks shorter than this


# ── Chunking ──────────────────────────────────────────────────────────────────
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks of fixed character length."""
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start : start + size].strip()
        chunks.append(chunk)
        start += size - overlap
    # Filter out tiny chunks that won't embed meaningfully
    return [c for c in chunks if len(c) >= MIN_CHUNK_LEN]


# ── Main Ingest ───────────────────────────────────────────────────────────────
def ingest():
    print("=" * 60)
    print("  Harsh Jaiswal Chatbot — Knowledge Base Ingestion")
    print("=" * 60)

    # 1. Load embedding model (downloads ~90MB on first run, cached after)
    print("\n[1/4] Loading embedding model (all-MiniLM-L6-v2)...")
    print("      First run downloads ~90MB — this is normal and only happens once.")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("      ✓ Model loaded.")

    # 2. Set up ChromaDB (wipe and recreate for clean re-ingest)
    print("\n[2/4] Setting up ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection(COLLECTION_NAME)
        print("      ✓ Cleared previous collection.")
    except Exception:
        print("      ✓ No previous collection found — starting fresh.")
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}   # use cosine similarity
    )

    # 3. Read and chunk all knowledge files
    print("\n[3/4] Reading knowledge files...")
    files = sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*.txt")))

    if not files:
        print("      ERROR: No .txt files found in knowledge/ folder!")
        print("      Make sure harsh.txt and qa_pairs.txt exist.")
        return

    all_chunks = []
    all_ids    = []
    all_meta   = []

    for fp in files:
        filename = os.path.basename(fp)
        text     = open(fp, encoding="utf-8").read()
        file_chunks = chunk_text(text)
        print(f"      {filename}: {len(text):,} chars → {len(file_chunks)} chunks")

        for i, chunk in enumerate(file_chunks):
            all_chunks.append(chunk)
            all_ids.append(f"{filename}_chunk_{i:04d}")
            all_meta.append({
                "source":      filename,
                "chunk_index": i,
                "file_path":   fp,
            })

    print(f"\n      Total: {len(all_chunks)} chunks across {len(files)} files")

    # 4. Embed and store
    print("\n[4/4] Embedding chunks and storing in ChromaDB...")
    print("      This may take 30–60 seconds on first run...")
    embeddings = model.encode(
        all_chunks,
        show_progress_bar=True,
        batch_size=32
    ).tolist()

    collection.add(
        documents=all_chunks,
        embeddings=embeddings,
        ids=all_ids,
        metadatas=all_meta,
    )

    print("\n" + "=" * 60)
    print(f"  ✓ SUCCESS: {len(all_chunks)} chunks stored in ChromaDB.")
    print(f"  ✓ Collection: '{COLLECTION_NAME}'")
    print(f"  ✓ Vector store: ./{CHROMA_PATH}/")
    print("=" * 60)
    print("\nNext step: uvicorn main:app --reload")
    print("Then visit: http://localhost:8000/docs\n")


if __name__ == "__main__":
    ingest()