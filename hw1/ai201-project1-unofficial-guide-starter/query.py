"""
query.py
========
Grounded RAG generation layer for the Unofficial Guide RAG system.

Pipeline stage this file covers:
    ChromaDB (Vector Store)
        -> Retrieval  [Top-5, distance threshold, sentence-transformers/all-MiniLM-L6-v2]
        -> Generation [Groq llama-3.3-70b-versatile]
        -> Response   {answer: str, sources: list[str], chunks_used: int, grounded: bool}

Grounding guarantee
-------------------
Grounding is enforced at TWO independent layers — not left to the LLM:

  Layer 1 — System prompt (instruction):
      The system prompt explicitly forbids the model from answering outside the
      provided context.  If the context is empty or insufficient, the model is
      told to return the exact sentinel string NO_GROUNDED_ANSWER rather than
      hallucinate.

  Layer 2 — Programmatic check (code):
      After generation, the code checks for the sentinel.  Source attribution
      is assembled entirely from the ChromaDB metadata returned by the vector
      search — the LLM never writes the source list.  Even if the LLM forgets
      to cite sources, the sources field in the returned dict is always correct
      because it comes from retrieval metadata, not from the model output.

Usage
-----
    from query import ask

    result = ask("What is self-attention in transformers?")
    print(result["answer"])
    print(result["sources"])   # always populated from retrieval, not from LLM

Environment variables (.env file)
----------------------------------
    GROQ_API_KEY=<your key>          # required
    CHROMA_PERSIST_DIR=./chroma_db   # optional, default shown
    CHROMA_COLLECTION=rag_collection # optional, default shown
    DISTANCE_THRESHOLD=0.55          # optional — chunks further than this are dropped
    TOP_K=5                          # optional
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TypedDict
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env (silently skip if python-dotenv not installed)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; set env vars manually if needed


# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------

GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL          = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Resolve chroma_db relative to this script file so it matches wherever
# ingest_and_chunk.py wrote it, regardless of terminal working directory.
_SCRIPT_DIR         = Path(__file__).resolve().parent
CHROMA_PERSIST_DIR  = os.getenv("CHROMA_PERSIST_DIR",
                                 str(_SCRIPT_DIR / "chroma_db"))
CHROMA_COLLECTION   = os.getenv("CHROMA_COLLECTION", "rag_collection")
EMBEDDING_MODEL     = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K               = int(os.getenv("TOP_K", "5"))
DISTANCE_THRESHOLD  = float(os.getenv("DISTANCE_THRESHOLD", "0.55"))

# Sentinel the model returns when it cannot answer from context
_NO_ANSWER_SENTINEL = "NO_GROUNDED_ANSWER"

# ---------------------------------------------------------------------------
# System prompt — grounding is ENFORCED, not suggested
# ---------------------------------------------------------------------------
# Critical design note:
#   "Try to answer from the context" is a suggestion — the LLM can ignore it.
#   The prompt below uses hard prohibitions + a specific fallback string so
#   grounding failures are detectable in code (see _is_grounded()).

_SYSTEM_PROMPT = f"""You are a precise academic assistant for a Computer Vision and Machine Learning course RAG system.

STRICT RULES — follow these exactly:

1. Answer ONLY using information that appears in the CONTEXT BLOCKS provided below.
2. Do NOT use any prior training knowledge, general knowledge, or information outside the provided context.
3. If the context does not contain enough information to answer the question, respond with exactly this string and nothing else:
   {_NO_ANSWER_SENTINEL}
4. Do NOT make up facts, fill in gaps from memory, or speculate.
5. Do NOT include a source list in your answer — sources are handled separately by the system.
6. Write your answer in clear, well-structured prose. Use bullet points or numbered lists only when the content genuinely calls for it.
7. Keep your answer focused and concise — do not pad with introductory phrases like "Based on the context..." or "According to the documents...".

These rules are absolute. Violation of rule 1, 2, or 3 is a grounding failure."""

_USER_PROMPT_TEMPLATE = """CONTEXT BLOCKS:
{context}

---

QUESTION:
{question}

ANSWER (from context only):"""


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class RAGResult(TypedDict):
    answer: str           # The model's answer, or a grounding-failure message
    sources: list[str]    # Programmatically assembled from retrieval metadata
    chunks_used: int      # Number of chunks that passed the distance threshold
    grounded: bool        # False if the sentinel was detected or no chunks found
    question: str         # Echo of the input question


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _load_retriever():
    """
    Load the ChromaDB collection and return a retriever callable.
    Lazy-loaded so import errors surface at query time with a clear message.
    """
    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    except ImportError:
        raise ImportError(
            "chromadb is not installed. Run: pip install chromadb sentence-transformers"
        )

    embed_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        collection = client.get_collection(
            name=CHROMA_COLLECTION,
            embedding_function=embed_fn,
        )
    except Exception:
        raise RuntimeError(
            f"ChromaDB collection '{CHROMA_COLLECTION}' not found at '{CHROMA_PERSIST_DIR}'.\n"
            "Run ingest_and_chunk.py first to build the vector store."
        )
    return collection


_collection = None  # module-level singleton — loaded once on first query


def retrieve(question: str) -> list[dict]:
    """
    Query ChromaDB and return chunks that pass the distance threshold.

    Each returned dict contains:
        text        : chunk text
        source_file : original PDF filename (from metadata)
        page_range  : page provenance (from metadata)
        distance    : cosine distance (lower = more similar)
    """
    global _collection
    if _collection is None:
        _collection = _load_retriever()

    results = _collection.query(
        query_texts=[question],
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(documents, metadatas, distances):
        if dist <= DISTANCE_THRESHOLD:
            chunks.append({
                "text":        doc,
                "source_file": meta.get("source_file", "unknown"),
                "page_range":  meta.get("page_range", ""),
                "distance":    round(dist, 4),
            })

    return chunks


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def _format_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into numbered context blocks for the prompt.
    Each block is labelled with its source so the model sees provenance
    (even though we never rely on the model to reproduce it).
    """
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        source = chunk["source_file"]
        pages  = chunk["page_range"]
        label  = f"[{i}] Source: {source}"
        if pages:
            label += f" | Pages: {pages}"
        blocks.append(f"{label}\n{chunk['text']}")
    return "\n\n---\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Source attribution (programmatic — never from LLM output)
# ---------------------------------------------------------------------------

def _build_sources(chunks: list[dict]) -> list[str]:
    """
    Build the deduplicated source list directly from retrieval metadata.
    This runs after generation and is independent of the model's output —
    the LLM cannot omit or fabricate sources.
    """
    seen = set()
    sources = []
    for chunk in chunks:
        label = chunk["source_file"]
        if chunk["page_range"]:
            label += f" ({chunk['page_range']})"
        if label not in seen:
            seen.add(label)
            sources.append(label)
    return sources


# ---------------------------------------------------------------------------
# Grounding check
# ---------------------------------------------------------------------------

def _is_grounded(answer: str) -> bool:
    """Return False if the model signalled it could not answer from context."""
    return _NO_ANSWER_SENTINEL not in answer.upper()


# ---------------------------------------------------------------------------
# LLM call (Groq)
# ---------------------------------------------------------------------------

def _call_groq(context: str, question: str) -> str:
    """Send the grounded prompt to Groq and return the model's raw text."""
    if not GROQ_API_KEY:
        raise EnvironmentError(
            "GROQ_API_KEY is not set. Add it to your .env file or environment."
        )
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("groq is not installed. Run: pip install groq")

    client = Groq(api_key=GROQ_API_KEY)
    user_message = _USER_PROMPT_TEMPLATE.format(
        context=context,
        question=question,
    )
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.0,   # deterministic — grounding requires no creativity
        max_tokens=1024,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(question: str) -> RAGResult:
    """
    End-to-end RAG query.

    Parameters
    ----------
    question : str
        The user's natural-language question.

    Returns
    -------
    RAGResult dict with keys:
        answer       : grounded answer string
        sources      : list of source attribution strings (from metadata, not LLM)
        chunks_used  : how many chunks passed the distance filter
        grounded     : True if the answer came from retrieved context
        question     : echo of the input
    """
    question = question.strip()
    if not question:
        return RAGResult(
            answer="Please enter a question.",
            sources=[],
            chunks_used=0,
            grounded=False,
            question=question,
        )

    # --- 1. Retrieve ---
    chunks = retrieve(question)

    if not chunks:
        return RAGResult(
            answer=(
                "I could not find relevant information in the course materials "
                "to answer this question. Try rephrasing or asking about a "
                "topic covered in the lecture notes."
            ),
            sources=[],
            chunks_used=0,
            grounded=False,
            question=question,
        )

    # --- 2. Format context ---
    context = _format_context(chunks)

    # --- 3. Generate ---
    raw_answer = _call_groq(context, question)

    # --- 4. Grounding check ---
    grounded = _is_grounded(raw_answer)

    if not grounded:
        answer = (
            "The retrieved course materials do not contain enough information "
            "to answer this question reliably. Please try a question more "
            "closely related to the lecture topics."
        )
    else:
        answer = raw_answer

    # --- 5. Programmatic source attribution (independent of LLM output) ---
    sources = _build_sources(chunks) if grounded else []

    return RAGResult(
        answer=answer,
        sources=sources,
        chunks_used=len(chunks),
        grounded=grounded,
        question=question,
    )


# ---------------------------------------------------------------------------
# CLI test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_questions = [
        "What is self-attention and how does it work in transformers?",
        "How does an autoencoder differ from PCA for dimensionality reduction?",
        "What are the main applications of autoencoders in computer vision?",
    ]

    print("=" * 70)
    print("RAG GROUNDED GENERATION — END-TO-END TEST")
    print("=" * 70)

    for i, q in enumerate(test_questions, start=1):
        print(f"\n[Query {i}] {q}")
        print("-" * 70)
        result = ask(q)
        print(f"Grounded     : {result['grounded']}")
        print(f"Chunks used  : {result['chunks_used']}")
        print(f"Sources      : {result['sources']}")
        print(f"\nAnswer:\n{result['answer']}")
        print("=" * 70)
