"""
signals/repetition.py — Signal 3: Lexical predictability heuristic.

Part of the Ensemble Detection stretch feature (3+ signals).

Measures use of "hedge/qualifier" and stock transitional vocabulary —
words and phrases disproportionately overrepresented in LLM output
relative to natural human writing at short-to-medium text lengths
(e.g. "numerous", "comprehensive", "furthermore", "it is important to
note"). This is a coarse, pure-Python proxy for the idea that AI text
is locally more "predictable" — it draws from a narrower, more formal
vocabulary of connective and qualifying language.

Calibration note
─────────────────
An earlier version of this signal used bigram repetition rate as the
primary statistic. Measuring it against the reference corpus showed it
does not discriminate at all at 30–45 word lengths — texts this short
rarely repeat any bigram, AI or human, so the statistic clustered at
0.0 for every text regardless of authorship. It was dropped in favor
of hedge-word density, which cleanly separated the corpus (AI: 2.4–14.0
hits per 100 words; human: 0.0 for all three reference texts).
"""

import re

# Hedge / formal-qualifier vocabulary disproportionately common in LLM output.
_HEDGE_WORDS = frozenset([
    "numerous", "various", "significant", "comprehensive", "essential",
    "crucial", "important", "fundamental", "extensively", "consistently",
    "effectively", "efficiently", "demonstrate", "demonstrates", "indicate",
    "indicates", "represents", "enables", "facilitate", "facilitates",
    "optimize", "optimizes", "leverage", "leverages", "utilize", "utilizes",
    "furthermore", "moreover", "additionally", "therefore", "consequently",
    "multifaceted", "cognizant", "underscore", "underscores",
])

# Multi-word stock phrases checked separately (substring match, not tokens).
_STOCK_PHRASES = [
    "it is important to note",
    "it is essential to",
    "it is worth noting",
    "in conclusion",
    "in summary",
    "on the other hand",
    "as previously mentioned",
    "in today's world",
    "plays a crucial role",
    "plays a significant role",
    "delve into",
    "navigate the complexities",
]

# Calibration anchors: (ai_end, human_end) — combined hedge density per 100 words.
# Derived from reference corpus: AI 2.4–14.0, human 0.0 for all three texts.
_CAL = {
    "hedge_density": (2.0, 0.0),   # ai_end=2.0 (low bar), human_end=0.0
}


def _normalise(value: float, ai_end: float, human_end: float) -> float:
    """Map value to [0,1] where ai_end -> 0.0 (AI-like), human_end -> 1.0 (human-like)."""
    span = human_end - ai_end
    if span == 0:
        return 0.5
    normalised = (value - ai_end) / span
    return max(0.0, min(1.0, normalised))


def _hedge_word_density(text: str) -> float:
    """Hedge-word hits per 100 words, including multi-word stock phrases."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    word_count = max(len(words), 1)

    single_hits = sum(1 for w in words if w in _HEDGE_WORDS)

    lower_text = text.lower()
    phrase_hits = sum(lower_text.count(phrase) for phrase in _STOCK_PHRASES)

    total_hits = single_hits + phrase_hits
    return (total_hits / word_count) * 100


def classify_repetition(text: str) -> dict:
    """
    Compute the lexical predictability score.

    Returns
    -------
    {
        "signal": "repetition",
        "score":  float,   # 0.0 (human-like) – 1.0 (AI-likely)
        "components": {
            "hedge_density": float,   # hits per 100 words
        }
    }
    """
    density = _hedge_word_density(text)
    human_likeness = _normalise(density, *_CAL["hedge_density"])
    ai_score = round(1.0 - human_likeness, 4)

    return {
        "signal": "repetition",
        "score": ai_score,
        "components": {
            "hedge_density": round(density, 4),
        },
    }
