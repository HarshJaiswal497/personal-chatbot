import chromadb
from sentence_transformers import SentenceTransformer

IN_SCOPE = [
    "What projects has Harsh built?",
    "Tell me about his internship at Cognizant",
    "What is Harsh's experience with Spring Boot?",
    "What programming languages does he know?",
    "What is his GPA?",
    "Has he worked with RAG or LLMs?",
    "What certifications does Harsh have?",
    "How many DSA problems has he solved?",
    "Tell me about the Runway project",
    "Does he know AWS or cloud?",
]
OUT_OF_SCOPE = [
    "What is Harsh's favourite food?",
    "What is the capital of France?",
    "Does Harsh have a pet?",
    "Who won the 2022 football world cup?",
    "What is his favourite movie?",
    "Write me a poem about the ocean",
    "What car does Harsh drive?",
    "How tall is Harsh?",
]

model = SentenceTransformer("all-MiniLM-L6-v2")
col = chromadb.PersistentClient(path="chroma_db").get_collection("harsh_knowledge")
print("space:", col.metadata)

for label, qs in (("IN", IN_SCOPE), ("OUT", OUT_OF_SCOPE)):
    for q in qs:
        r = col.query(query_embeddings=model.encode([q]).tolist(), n_results=1,
                      include=["distances", "metadatas"])
        d = r["distances"][0][0]
        print(f"{label:3} new={1 - d:.3f} old={1 / (1 + d):.3f}  {q}  [{r['metadatas'][0][0]['source']}]")
