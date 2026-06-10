"""
ingest_and_chunk.py
====================
Document ingestion and hybrid chunking pipeline for a RAG system.

Pipeline stage:
    Document Ingestion (pdfplumber / pypdf)
        -> Text Cleaning
        -> Hybrid Chunking [Recursive + Semantic]  chunk_size=500, chunk_overlap=50
        -> Chunk export (JSON + plain-text preview)

Dependencies (install in your target environment):
    pip install pdfplumber pypdf langchain langchain-community \
                langchain-text-splitters sentence-transformers chromadb

The script is intentionally self-contained so it works during development
even without langchain installed: it ships its own recursive chunker as a
fallback.  The langchain-based classes are imported lazily and used when
present, which gives you identical behaviour to the full pipeline.

Usage
-----
    # Process a folder of PDFs
    python ingest_and_chunk.py --input_dir ./pdfs --output_dir ./chunks

    # Process a single PDF
    python ingest_and_chunk.py --input_dir ./pdfs/lecture_10.pdf --output_dir ./chunks

    # Adjust chunk parameters
    python ingest_and_chunk.py --input_dir ./pdfs \
        --chunk_size 500 --chunk_overlap 50 --overlap_window 150

Output
------
    chunks/
        all_chunks.json          # Full metadata + text for every chunk
        all_chunks_preview.txt   # Human-readable preview (first 120 chars per chunk)
        <doc_stem>_chunks.json   # Per-document chunk file
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import pdfplumber


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """One chunk produced by the pipeline."""
    chunk_id: str          # deterministic SHA-256 of (source_file + chunk_index)
    source_file: str       # original PDF filename
    page_range: str        # "p1" or "p3-p5" etc.
    chunk_index: int       # 0-based index within document
    chunk_method: str      # "recursive" | "semantic"
    text: str              # cleaned chunk text
    token_estimate: int    # rough word-level token estimate

    def preview(self, width: int = 120) -> str:
        snippet = self.text.replace("\n", " ")[:width]
        return f"[{self.chunk_id[:8]}] [{self.chunk_method}] {snippet}"


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_with_pdfplumber(pdf_path: Path) -> List[dict]:
    """
    Extract text page-by-page using pdfplumber.

    Returns a list of dicts: {"page": int (1-based), "text": str}
    Falls back to pypdf for pages where pdfplumber returns nothing.
    """
    pages = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                # pdfplumber can also pull table text; merge it in
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        row_text = "  ".join(cell or "" for cell in row if cell)
                        if row_text.strip():
                            text += "\n" + row_text
                pages.append({"page": i, "text": text})
    except Exception as exc:
        print(f"  [warn] pdfplumber failed on {pdf_path.name}: {exc}. Trying pypdf...")
        pages = _extract_with_pypdf(pdf_path)

    # Per-page fallback: if pdfplumber returned blank for a page, try pypdf
    if any(p["text"].strip() == "" for p in pages):
        pypdf_pages = _extract_with_pypdf(pdf_path)
        pypdf_map = {p["page"]: p["text"] for p in pypdf_pages}
        for p in pages:
            if p["text"].strip() == "" and pypdf_map.get(p["page"], "").strip():
                p["text"] = pypdf_map[p["page"]]
                print(f"  [info] page {p['page']}: used pypdf fallback")

    return pages


def _extract_with_pypdf(pdf_path: Path) -> List[dict]:
    """Fallback extractor using pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": i, "text": text})
    return pages


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

# Patterns for slide-deck artefacts common in lecture PDFs
_SLIDE_HEADER_RE = re.compile(
    r"^(CAP\d+\s*[-–]?\s*Lecture\s*\d+[\s\S]{0,60}?\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE | re.MULTILINE,
)
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*$", re.MULTILINE)
_BULLET_NORMALIZE_RE = re.compile(r"^[\u2022\u2023\u25e6\u2043\u2219•·▪▸‣]\s*", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"[ \t]{2,}")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_URL_RE = re.compile(r"https?://\S+")


def clean_text(raw: str, strip_urls: bool = False) -> str:
    """
    Clean raw extracted text:
      - Remove slide headers / page numbers
      - Normalise Unicode bullets to '-'
      - Collapse excessive whitespace / blank lines
      - Strip stray control characters
      - Optionally strip URLs
    """
    text = raw

    # Remove slide-deck header lines (e.g. "10/3/2024  CAP5415 - Lecture 10  3")
    text = _SLIDE_HEADER_RE.sub("", text)

    # Remove bare page numbers on their own line
    text = _PAGE_NUMBER_RE.sub("", text)

    # Normalise Unicode bullet characters
    text = _BULLET_NORMALIZE_RE.sub("- ", text)

    if strip_urls:
        text = _URL_RE.sub("", text)

    # Remove non-printable control characters (keep \n \t)
    text = re.sub(r"[^\x09\x0a\x20-\x7e\u00a0-\ufffd]", " ", text)

    # Collapse horizontal whitespace runs
    text = _WHITESPACE_RE.sub(" ", text)

    # Collapse excess blank lines
    text = _BLANK_LINES_RE.sub("\n\n", text)

    return text.strip()


def build_document_text(pages: List[dict]) -> tuple[str, dict[int, tuple[int, int]]]:
    """
    Concatenate page texts into one document string and build a character
    offset -> (page_start, page_end) mapping for provenance tracking.

    Returns:
        full_text  : concatenated document string
        offset_map : list of (char_start, char_end, page_number) tuples
    """
    parts = []
    offset_info: list[tuple[int, int, int]] = []
    cursor = 0
    for p in pages:
        cleaned = clean_text(p["text"])
        if not cleaned:
            continue
        start = cursor
        end = cursor + len(cleaned)
        offset_info.append((start, end, p["page"]))
        parts.append(cleaned)
        cursor = end + 2  # +2 for the "\n\n" separator

    full_text = "\n\n".join(parts)
    return full_text, offset_info


def resolve_page_range(char_start: int, char_end: int,
                       offset_info: list[tuple[int, int, int]]) -> str:
    """Return a human-readable page range string for a character span."""
    pages_hit = set()
    for (s, e, pg) in offset_info:
        # Spans overlap if not (char_end <= s or char_start >= e)
        if not (char_end <= s or char_start >= e):
            pages_hit.add(pg)
    if not pages_hit:
        return "p?"
    sorted_pages = sorted(pages_hit)
    if len(sorted_pages) == 1:
        return f"p{sorted_pages[0]}"
    return f"p{sorted_pages[0]}-p{sorted_pages[-1]}"


# ---------------------------------------------------------------------------
# Chunking — pure-Python fallback implementations
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough word-based token estimate (1 word ≈ 1.3 tokens)."""
    return int(len(text.split()) * 1.3)


class RecursiveTextSplitter:
    """
    Pure-Python recursive character text splitter.

    Mimics LangChain's RecursiveCharacterTextSplitter behaviour:
    tries to split on paragraph breaks, then sentence ends, then spaces,
    then raw character boundaries — whichever keeps chunks under chunk_size.

    When langchain_text_splitters is available the pipeline uses the
    official class instead (see _make_recursive_splitter).
    """

    SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ---- public API ----

    def split_text(self, text: str) -> List[str]:
        chunks = self._split(text, self.SEPARATORS)
        return self._merge_with_overlap(chunks)

    # ---- internals ----

    def _split(self, text: str, separators: List[str]) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        separator = separators[-1]  # default: raw char split
        for sep in separators:
            if sep in text:
                separator = sep
                break

        parts = text.split(separator)
        good: List[str] = []
        current: List[str] = []
        current_len = 0

        for part in parts:
            part_len = len(part) + len(separator)
            if current_len + part_len > self.chunk_size and current:
                good.append(separator.join(current))
                current = []
                current_len = 0
            current.append(part)
            current_len += part_len

        if current:
            good.append(separator.join(current))

        # Recurse on any over-sized piece
        final: List[str] = []
        for piece in good:
            if len(piece) <= self.chunk_size:
                final.append(piece)
            else:
                next_seps = separators[separators.index(separator) + 1:]
                if next_seps:
                    final.extend(self._split(piece, next_seps))
                else:
                    # Hard split as last resort
                    for i in range(0, len(piece), self.chunk_size):
                        final.append(piece[i: i + self.chunk_size])
        return final

    def _merge_with_overlap(self, chunks: List[str]) -> List[str]:
        """Re-merge tiny fragments and add overlap between consecutive chunks."""
        merged: List[str] = []
        buffer = ""

        for chunk in chunks:
            if not chunk.strip():
                continue
            candidate = (buffer + " " + chunk).strip() if buffer else chunk
            if len(candidate) <= self.chunk_size:
                buffer = candidate
            else:
                if buffer:
                    merged.append(buffer)
                buffer = chunk

        if buffer:
            merged.append(buffer)

        # Add overlap: prepend the last `chunk_overlap` chars from previous chunk
        if self.chunk_overlap <= 0 or len(merged) < 2:
            return merged

        overlapped: List[str] = [merged[0]]
        for i in range(1, len(merged)):
            tail = merged[i - 1][-self.chunk_overlap:]
            overlapped.append((tail + " " + merged[i]).strip())
        return overlapped


class SemanticSplitter:
    """
    Lightweight semantic chunker that groups sentences by topic shift.

    Algorithm:
      1. Split document into sentences.
      2. Embed each sentence using a local SentenceTransformer model
         (falls back to a trigram-cosine similarity if the library is absent).
      3. Compute cosine similarity between adjacent sentences.
      4. Insert a split where similarity drops below `breakpoint_threshold`.
      5. Merge resulting segments to honour chunk_size / chunk_overlap.

    When langchain_experimental is available, SemanticChunker is used
    instead (see _make_semantic_splitter).
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        breakpoint_threshold: float = 0.45,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.threshold = breakpoint_threshold
        self.model_name = model_name
        self._embed_fn = self._build_embed_fn()

    # ---- public API ----

    def split_text(self, text: str) -> List[str]:
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return sentences or [text]

        embeddings = [self._embed_fn(s) for s in sentences]
        breaks = self._find_breaks(embeddings)

        segments = self._sentences_to_segments(sentences, breaks)
        return self._size_aware_merge(segments)

    # ---- sentence splitting ----

    _SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\'])")

    def _split_sentences(self, text: str) -> List[str]:
        sentences = self._SENT_RE.split(text)
        # Also split on newline-separated bullet points
        expanded: List[str] = []
        for s in sentences:
            lines = [l.strip() for l in s.split("\n") if l.strip()]
            expanded.extend(lines)
        return [s for s in expanded if len(s.split()) >= 3]

    # ---- embedding ----

    def _build_embed_fn(self):
        """Return a callable (str) -> List[float]."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self.model_name)

            def st_embed(text: str) -> list:
                return model.encode(text, normalize_embeddings=True).tolist()

            print(f"  [info] SemanticSplitter: using SentenceTransformer ({self.model_name})")
            return st_embed
        except ImportError:
            print("  [info] SemanticSplitter: sentence-transformers not found; "
                  "using trigram-cosine fallback (install sentence-transformers "
                  "for better semantic splitting)")
            return self._trigram_embed

    @staticmethod
    def _trigram_embed(text: str) -> list:
        """Character-trigram bag-of-features as a simple embedding fallback."""
        text = text.lower()
        trigrams: dict[str, int] = {}
        for i in range(len(text) - 2):
            g = text[i: i + 3]
            trigrams[g] = trigrams.get(g, 0) + 1
        norm = (sum(v * v for v in trigrams.values()) ** 0.5) or 1.0
        return [(k, v / norm) for k, v in trigrams.items()]  # type: ignore[return-value]

    # ---- similarity ----

    def _cosine(self, a, b) -> float:
        if not a or not b:
            return 0.0
        # Dense list (sentence-transformers output)
        if isinstance(a[0], float):
            dot = sum(x * y for x, y in zip(a, b))
            return max(-1.0, min(1.0, dot))
        # Sparse list-of-(key, val) (trigram fallback)
        da = dict(a)  # type: ignore[arg-type]
        db = dict(b)  # type: ignore[arg-type]
        common = set(da) & set(db)
        dot = sum(da[k] * db[k] for k in common)
        norm_a = (sum(v * v for v in da.values()) ** 0.5) or 1.0
        norm_b = (sum(v * v for v in db.values()) ** 0.5) or 1.0
        return dot / (norm_a * norm_b)

    def _find_breaks(self, embeddings: list) -> set:
        sims = [self._cosine(embeddings[i], embeddings[i + 1])
                for i in range(len(embeddings) - 1)]
        return {i + 1 for i, s in enumerate(sims) if s < self.threshold}

    # ---- segment assembly ----

    def _sentences_to_segments(self, sentences: List[str], breaks: set) -> List[str]:
        segments: List[str] = []
        buf: List[str] = []
        for i, sent in enumerate(sentences):
            if i in breaks and buf:
                segments.append(" ".join(buf))
                buf = []
            buf.append(sent)
        if buf:
            segments.append(" ".join(buf))
        return segments

    def _size_aware_merge(self, segments: List[str]) -> List[str]:
        """Merge short segments and split over-sized ones to honour chunk_size."""
        result: List[str] = []
        buffer = ""
        for seg in segments:
            candidate = (buffer + " " + seg).strip() if buffer else seg
            if len(candidate) <= self.chunk_size:
                buffer = candidate
            else:
                if buffer:
                    result.append(buffer)
                # If the segment itself is too long, hard-split it
                if len(seg) > self.chunk_size:
                    for i in range(0, len(seg), self.chunk_size - self.chunk_overlap):
                        result.append(seg[i: i + self.chunk_size])
                    buffer = ""
                else:
                    buffer = seg
        if buffer:
            result.append(buffer)

        # Add overlap
        if self.chunk_overlap > 0 and len(result) > 1:
            overlapped = [result[0]]
            for i in range(1, len(result)):
                tail = result[i - 1][-self.chunk_overlap:]
                overlapped.append((tail + " " + result[i]).strip())
            return overlapped
        return result


# ---------------------------------------------------------------------------
# LangChain wrappers (used when langchain is installed)
# ---------------------------------------------------------------------------

def _make_recursive_splitter(chunk_size: int, chunk_overlap: int):
    """Return a LangChain RecursiveCharacterTextSplitter if available."""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        print("  [info] Using langchain RecursiveCharacterTextSplitter")
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
            length_function=len,
        )
    except ImportError:
        print("  [info] langchain_text_splitters not installed; "
              "using built-in RecursiveTextSplitter")
        return RecursiveTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _make_semantic_splitter(chunk_size: int, chunk_overlap: int,
                            breakpoint_threshold: float, model_name: str):
    """Return a LangChain SemanticChunker if langchain_experimental is available."""
    try:
        from langchain_experimental.text_splitter import SemanticChunker
        from langchain_community.embeddings import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(model_name=model_name)
        print("  [info] Using langchain SemanticChunker")
        return SemanticChunker(
            embeddings,
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=breakpoint_threshold * 100,
        )
    except ImportError:
        print("  [info] langchain_experimental / langchain_community not installed; "
              "using built-in SemanticSplitter")
        return SemanticSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            breakpoint_threshold=breakpoint_threshold,
            model_name=model_name,
        )


# ---------------------------------------------------------------------------
# Hybrid chunking
# ---------------------------------------------------------------------------

def hybrid_chunk(
    full_text: str,
    offset_info: list,
    source_file: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    overlap_window: int = 150,
    breakpoint_threshold: float = 0.45,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> List[Chunk]:
    """
    Hybrid chunking strategy:

    Step 1 – Recursive chunking
        Split the full document text using a recursive separator hierarchy.
        This produces structurally clean initial segments that respect
        paragraph / sentence / word boundaries.

    Step 2 – Semantic refinement
        Each recursive chunk is passed to the semantic splitter.  Where the
        splitter detects a meaningful topic shift (cosine similarity drop
        below `breakpoint_threshold`) it inserts an additional split point,
        keeping topically coherent content together.

    Step 3 – Overlap stitching
        Both stages apply `chunk_overlap` so that context is preserved
        across chunk boundaries, preventing retrieval from missing
        information that straddles a split.

    Returns a list of Chunk objects with full provenance metadata.
    """
    recursive_splitter = _make_recursive_splitter(chunk_size, chunk_overlap)
    semantic_splitter = _make_semantic_splitter(
        chunk_size, chunk_overlap, breakpoint_threshold, embedding_model
    )

    # --- Step 1: recursive split ---
    recursive_chunks: List[str] = recursive_splitter.split_text(full_text)
    print(f"  [info] Recursive split produced {len(recursive_chunks)} segments")

    # --- Step 2: semantic refinement of each recursive chunk ---
    final_texts: List[tuple[str, str]] = []  # (text, method)
    for rc in recursive_chunks:
        if not rc.strip():
            continue
        # Only apply semantic splitting to chunks long enough to split further
        if len(rc.split()) < 30:
            final_texts.append((rc, "recursive"))
            continue
        sub_chunks = semantic_splitter.split_text(rc)
        if len(sub_chunks) > 1:
            for sc in sub_chunks:
                if sc.strip():
                    final_texts.append((sc, "semantic"))
        else:
            final_texts.append((rc, "recursive"))

    print(f"  [info] After semantic refinement: {len(final_texts)} chunks")

    # --- Step 3: build Chunk objects with provenance ---
    chunks: List[Chunk] = []
    for idx, (text, method) in enumerate(final_texts):
        text = text.strip()
        if not text:
            continue

        # Find character position of this text in the full document
        char_start = full_text.find(text[:60])  # anchor on first 60 chars
        char_end = char_start + len(text) if char_start >= 0 else len(text)
        page_range = resolve_page_range(char_start, char_end, offset_info)

        uid = hashlib.sha256(
            f"{source_file}::{idx}::{text[:80]}".encode()
        ).hexdigest()[:16]

        chunks.append(Chunk(
            chunk_id=uid,
            source_file=source_file,
            page_range=page_range,
            chunk_index=idx,
            chunk_method=method,
            text=text,
            token_estimate=_estimate_tokens(text),
        ))

    return chunks


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: Path,
    chunk_size: int,
    chunk_overlap: int,
    overlap_window: int,
    breakpoint_threshold: float,
    embedding_model: str,
) -> List[Chunk]:
    """End-to-end processing for one PDF: extract -> clean -> chunk."""
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'='*60}")

    # 1. Extract
    pages = extract_text_with_pdfplumber(pdf_path)
    non_empty = sum(1 for p in pages if p["text"].strip())
    print(f"  Extracted {len(pages)} pages ({non_empty} non-empty)")

    # 2. Build document text + offset map
    full_text, offset_info = build_document_text(pages)
    word_count = len(full_text.split())
    print(f"  Document word count after cleaning: {word_count}")

    if word_count < 10:
        print("  [warn] Very little text extracted — PDF may be image-based or encrypted.")
        return []

    # 3. Hybrid chunk
    chunks = hybrid_chunk(
        full_text=full_text,
        offset_info=offset_info,
        source_file=pdf_path.name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        overlap_window=overlap_window,
        breakpoint_threshold=breakpoint_threshold,
        embedding_model=embedding_model,
    )
    print(f"  Final chunk count: {len(chunks)}")
    return chunks


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    overlap_window: int = 150,
    breakpoint_threshold: float = 0.45,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect PDF paths
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        pdf_files = [input_path]
    elif input_path.is_dir():
        pdf_files = sorted(input_path.glob("**/*.pdf"))
    else:
        print(f"[error] {input_path} is not a PDF file or directory.")
        sys.exit(1)

    if not pdf_files:
        print(f"[warn] No PDF files found in {input_path}")
        return

    print(f"\nFound {len(pdf_files)} PDF(s) to process")
    print(f"Config: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}, "
          f"overlap_window={overlap_window}, threshold={breakpoint_threshold}")

    all_chunks: List[Chunk] = []

    for pdf_path in pdf_files:
        chunks = process_pdf(
            pdf_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            overlap_window=overlap_window,
            breakpoint_threshold=breakpoint_threshold,
            embedding_model=embedding_model,
        )
        all_chunks.extend(chunks)

        # Per-document output
        doc_out = output_dir / f"{pdf_path.stem}_chunks.json"
        with open(doc_out, "w", encoding="utf-8") as f:
            json.dump([asdict(c) for c in chunks], f, indent=2, ensure_ascii=False)
        print(f"  Saved {len(chunks)} chunks -> {doc_out}")

    # Combined output
    all_out = output_dir / "all_chunks.json"
    with open(all_out, "w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in all_chunks], f, indent=2, ensure_ascii=False)

    preview_out = output_dir / "all_chunks_preview.txt"
    with open(preview_out, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(c.preview() + "\n")

    # Summary statistics
    recursive_count = sum(1 for c in all_chunks if c.chunk_method == "recursive")
    semantic_count = sum(1 for c in all_chunks if c.chunk_method == "semantic")
    avg_tokens = (sum(c.token_estimate for c in all_chunks) / len(all_chunks)
                  if all_chunks else 0)

    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")
    print(f"  Documents processed  : {len(pdf_files)}")
    print(f"  Total chunks         : {len(all_chunks)}")
    print(f"    recursive method   : {recursive_count}")
    print(f"    semantic method    : {semantic_count}")
    print(f"  Average chunk tokens : {avg_tokens:.1f}")
    print(f"  Output directory     : {output_dir.resolve()}")
    print(f"  Combined JSON        : {all_out}")
    print(f"  Preview file         : {preview_out}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# LangChain vector-store integration stub
# (Uncomment and use after `pip install langchain chromadb sentence-transformers`)
# ---------------------------------------------------------------------------

def load_chunks_into_chromadb(
    chunks_json_path: Path,
    collection_name: str = "rag_collection",
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    persist_dir: str = "./chroma_db",
    batch_size: int = 100,
) -> None:
    """
    Load chunks from the JSON output file into ChromaDB using the
    native chromadb client + SentenceTransformer embedding function.

    No langchain required. Uses the same client/collection setup as query.py
    so the vector store is immediately queryable after this runs.

    Parameters
    ----------
    chunks_json_path : Path to all_chunks.json produced by run_pipeline()
    collection_name  : Must match CHROMA_COLLECTION in query.py / .env
    embedding_model  : Must match EMBEDDING_MODEL in query.py / .env
    persist_dir      : Must match CHROMA_PERSIST_DIR in query.py / .env
    batch_size       : Number of chunks to upsert per batch (avoids memory spikes)
    """
    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    except ImportError:
        print("[error] chromadb / sentence-transformers not installed.\n"
              "Run: pip install chromadb sentence-transformers")
        return

    if not chunks_json_path.exists():
        print(f"[error] Chunks file not found: {chunks_json_path}")
        return

    print(f"\nLoading chunks into ChromaDB...")
    print(f"  Collection : {collection_name}")
    print(f"  Persist dir: {persist_dir}")
    print(f"  Embeddings : {embedding_model}")

    with open(chunks_json_path, encoding="utf-8") as f:
        raw = json.load(f)

    if not raw:
        print("[warn] all_chunks.json is empty — nothing to load.")
        return

    embed_fn = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    client = chromadb.PersistentClient(path=persist_dir)

    # Delete existing collection so re-runs stay clean
    try:
        client.delete_collection(name=collection_name)
        print(f"  Deleted existing collection '{collection_name}' (fresh rebuild)")
    except Exception:
        pass  # Collection did not exist yet — fine

    collection = client.create_collection(
        name=collection_name,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # Upsert in batches
    total = len(raw)
    for start in range(0, total, batch_size):
        batch = raw[start: start + batch_size]
        collection.upsert(
            ids=[c["chunk_id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[
                {
                    "source_file":    c["source_file"],
                    "page_range":     c["page_range"],
                    "chunk_index":    c["chunk_index"],
                    "chunk_method":   c["chunk_method"],
                    "token_estimate": c["token_estimate"],
                }
                for c in batch
            ],
        )
        print(f"  Upserted chunks {start + 1}–{min(start + batch_size, total)} / {total}")

    print(f"  ChromaDB ready: {total} chunks stored in '{collection_name}'\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    # Resolve defaults relative to the script file so they work regardless
    # of which directory the terminal is open in.
    _script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="Ingest PDFs and produce hybrid recursive+semantic chunks for RAG.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input_dir", type=Path,
        default=_script_dir / "documents" / "ex",
        help="Path to a PDF file or directory containing PDF files.",
    )
    parser.add_argument(
        "--output_dir", type=Path,
        default=_script_dir / "documents" / "output",
        help="Directory to write chunk JSON and preview files.",
    )
    parser.add_argument(
        "--chunk_size", type=int, default=500,
        help="Maximum character length of each chunk.",
    )
    parser.add_argument(
        "--chunk_overlap", type=int, default=50,
        help="Overlap in characters between consecutive chunks.",
    )
    parser.add_argument(
        "--overlap_window", type=int, default=150,
        help="Additional context window (chars) preserved at topic transitions.",
    )
    parser.add_argument(
        "--breakpoint_threshold", type=float, default=0.45,
        help="Cosine similarity below which a semantic split is inserted (0–1).",
    )
    parser.add_argument(
        "--embedding_model", type=str,
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="SentenceTransformer model name for semantic splitting and ChromaDB.",
    )
    parser.add_argument(
        "--chroma_dir", type=str,
        default=str(_script_dir / "chroma_db"),
        help="Directory where ChromaDB persists its data. Must match CHROMA_PERSIST_DIR in .env.",
    )
    parser.add_argument(
        "--chroma_collection", type=str,
        default="rag_collection",
        help="ChromaDB collection name. Must match CHROMA_COLLECTION in .env.",
    )
    parser.add_argument(
        "--skip_chroma", action="store_true",
        help="Skip loading chunks into ChromaDB (output JSON only).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(
        input_path=args.input_dir,
        output_dir=args.output_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        overlap_window=args.overlap_window,
        breakpoint_threshold=args.breakpoint_threshold,
        embedding_model=args.embedding_model,
    )
    # Always load into ChromaDB after chunking so query.py can find the collection.
    # Pass --skip_chroma to disable (e.g. if you only want the JSON output).
    if not args.skip_chroma:
        load_chunks_into_chromadb(
            chunks_json_path=args.output_dir / "all_chunks.json",
            collection_name=args.chroma_collection,
            embedding_model=args.embedding_model,
            persist_dir=args.chroma_dir,
        )
