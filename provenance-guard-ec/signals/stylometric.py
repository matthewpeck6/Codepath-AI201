"""
signals/stylometric.py — Signal 2: Stylometric heuristics (pure Python).

Computes four structural statistics, normalises each to [0.0, 1.0],
and returns a single score in [0.0, 1.0] where 1.0 = AI-likely.

Statistics (v2 — recalibrated from corpus of 6 reference texts)
────────────────────────────────────────────────────────────────
1. Average word length        — AI uses longer, more formal vocabulary
2. Sentence length variance   — SD of per-sentence word counts
3. Punctuation density        — punctuation chars / total chars
4. Subordinate clause ratio   — sentences with subordinating cue words

Why TTR was dropped
───────────────────
Type-token ratio (TTR) is highly sensitive to text length: at the 80–150
word range typical of short submissions, nearly all text — AI or human —
achieves a TTR of 0.74–0.84, providing almost no discriminating signal.
Average word length proved more reliable across the reference corpus and
is not length-sensitive.

Calibration ranges (ai_end → 0.0, human_end → 1.0)
────────────────────────────────────────────────────
Derived from corpus of 3 clearly-AI and 3 clearly-human texts.

  Statistic             ai_end   human_end   discrimination
  ──────────────────── ───────── ─────────── ──────────────
  avg_word_length       6.5      4.0         strong  (AI 6.0–6.4 vs Human 4.1–4.5)
  sentence_variance     2.0      9.0         strong  (AI 2.9–5.4 vs Human 5.1–7.4)
  punct_density         0.015    0.035       moderate
  subordinate_ratio     0.05     0.70        moderate (confounded by formal human)
"""

import math
import re
import string

# Calibration anchors: (ai_end, human_end)
# ai_end  → normalised 0.0  (AI-like)
# human_end → normalised 1.0 (human-like)
_CAL = {
    "avg_word_length":    (6.5, 4.0),   # inverted: higher = more AI
    "sentence_variance":  (2.0, 9.0),
    "punct_density":      (0.015, 0.035),
    "subordinate_ratio":  (0.05, 0.70),
}

# Cue words that suggest a subordinate clause
_SUBORDINATE_CUES = frozenset([
    "which", "who", "whom", "whose",
    "although", "though", "even",
    "because", "since",
    "while", "whilst",
    "if", "unless", "until",
    "when", "whenever", "where", "wherever",
    "that", "whether", "as",
])


def _normalise(value: float, ai_end: float, human_end: float) -> float:
    """
    Linearly map `value` from [ai_end, human_end] to [0.0, 1.0].
    ai_end → 0.0  (AI-like),  human_end → 1.0  (human-like).
    Result is clipped to [0.0, 1.0].
    """
    span = human_end - ai_end
    if span == 0:
        return 0.5
    normalised = (value - ai_end) / span
    return max(0.0, min(1.0, normalised))


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter on .  !  ? followed by whitespace or EOL."""
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in raw if s.strip()]


def _tokenise_words(text: str) -> list[str]:
    """Lowercase alphabetic word tokens only."""
    return re.findall(r"\b[a-zA-Z]+\b", text)


# ── Individual statistics ──────────────────────────────────────────────────────

def _compute_avg_word_length(text: str) -> float:
    """Average character length of alphabetic words. Empty → 4.5 (neutral)."""
    words = _tokenise_words(text)
    if not words:
        return 4.5
    return sum(len(w) for w in words) / len(words)


def _compute_sentence_variance(sentences: list[str]) -> float:
    """Standard deviation of sentence word counts. < 2 sentences → 0.0."""
    lengths = [len(s.split()) for s in sentences]
    if len(lengths) < 2:
        return 0.0
    mean = sum(lengths) / len(lengths)
    variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return math.sqrt(variance)


def _compute_punct_density(text: str) -> float:
    """Punctuation chars / total chars. Empty → 0.0."""
    if not text:
        return 0.0
    punct_chars = sum(1 for ch in text if ch in string.punctuation)
    return punct_chars / len(text)


def _compute_subordinate_ratio(sentences: list[str]) -> float:
    """
    Fraction of sentences containing at least one subordinating cue word.
    Empty → 0.0.
    """
    if not sentences:
        return 0.0
    hits = 0
    for sent in sentences:
        words = set(re.findall(r"\b[a-z]+\b", sent.lower()))
        if words & _SUBORDINATE_CUES:
            hits += 1
    return hits / len(sentences)


# ── Public API ─────────────────────────────────────────────────────────────────

def classify_stylometric(text: str) -> dict:
    """
    Compute stylometric statistics and return a result dict.

    Returns
    -------
    {
        "signal":     "stylometric",
        "score":      float,   # 0.0 (human-like) – 1.0 (AI-likely)
        "components": {
            "avg_word_length":   float,  # raw stat
            "sentence_variance": float,
            "punct_density":     float,
            "subordinate_ratio": float,
        }
    }
    """
    sentences = _split_sentences(text)

    raw = {
        "avg_word_length":   _compute_avg_word_length(text),
        "sentence_variance": _compute_sentence_variance(sentences),
        "punct_density":     _compute_punct_density(text),
        "subordinate_ratio": _compute_subordinate_ratio(sentences),
    }

    # Normalise each stat to [0.0, 1.0] where 1.0 = human-like
    normalised = {
        key: _normalise(val, *_CAL[key])
        for key, val in raw.items()
    }

    # Average normalised human-likeness scores, then invert so 1.0 = AI-likely
    human_likeness = sum(normalised.values()) / len(normalised)
    ai_score = round(1.0 - human_likeness, 4)

    return {
        "signal":     "stylometric",
        "score":      ai_score,
        "components": {k: round(v, 4) for k, v in raw.items()},
    }
