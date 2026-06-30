"""
scoring.py — Confidence scoring and transparency label generation.

Combines Signal 1 (LLM) and Signal 2 (stylometric) into a single
confidence score, then maps that score to a transparency label variant.

Thresholds (from planning.md)
─────────────────────────────
  score ≥ 0.80  →  high_confidence_ai    (Variant A)
  score ≤ 0.20  →  high_confidence_human (Variant B)
  otherwise     →  uncertain             (Variant C)

The 0.80 / 0.20 asymmetry is a deliberate fairness decision: on a writing
platform a false positive (accusing a human) is more harmful than a false
negative, so borderline cases default to "uncertain" rather than "accused."

Weights
───────
  Long text  (≥ 80 words): 60% LLM  +  40% stylometric
  Short text (< 80 words): 50% LLM  +  50% stylometric
"""

# ── Label text strings (exact copy from planning.md Milestone 2) ────────────

_LABEL_AI = (
    "Our analysis suggests this content was likely written with AI assistance. "
    "Confidence: high. "
    "Detection systems are not perfect. If you are the author and believe this "
    "is incorrect, you can contest this finding using the appeal option below."
)

_LABEL_HUMAN = (
    "This content shows strong indicators of human authorship. "
    "No significant AI involvement detected. Confidence: high."
)

# Variant C includes the numeric score; format it in before returning.
_LABEL_UNCERTAIN_TEMPLATE = (
    "Our system could not confidently determine the authorship of this content "
    "(confidence score: {score_pct}%). "
    "The signals were mixed or inconclusive. "
    "This is not a finding of AI use. Authors can provide additional context "
    "using the appeal option below."
)

# Short-text override: always uncertain regardless of raw score.
_LABEL_SHORT_TEXT = (
    "Our system could not confidently determine the authorship of this content. "
    "The submission is too short for a reliable verdict. "
    "This is not a finding of AI use. Authors can provide additional context "
    "using the appeal option below."
)

SHORT_TEXT_THRESHOLD = 40   # words
AI_THRESHOLD         = 0.80
HUMAN_THRESHOLD      = 0.20


def compute_confidence(llm_score: float, stylo_score: float,
                        word_count: int) -> float:
    """
    Combine Signal 1 and Signal 2 scores into a single confidence float.
    Retained for backward compatibility / the 2-signal path.

    Parameters
    ----------
    llm_score    : float in [0.0, 1.0] from signals/llm.py
    stylo_score  : float in [0.0, 1.0] from signals/stylometric.py
    word_count   : number of words in the submitted text

    Returns
    -------
    float in [0.0, 1.0] — probability the content is AI-generated.
    """
    if word_count < SHORT_TEXT_THRESHOLD:
        # 50/50 for short texts; LLM signal is less reliable here
        combined = 0.50 * llm_score + 0.50 * stylo_score
    else:
        combined = 0.60 * llm_score + 0.40 * stylo_score

    return round(max(0.0, min(1.0, combined)), 4)


def compute_confidence_ensemble(llm_score: float, stylo_score: float,
                                 repetition_score: float,
                                 word_count: int) -> float:
    """
    Combine all three signals into a single confidence float.

    [STRETCH FEATURE — Ensemble detection]

    Weighted voting scheme:
        combined = 0.50 × llm_score + 0.30 × stylo_score + 0.20 × repetition_score

    LLM keeps the largest weight as the most semantically informed signal.
    Stylometric keeps a substantial weight as the validated structural signal.
    Repetition gets the smallest weight — it is the newest, least-validated
    signal, included as a tie-breaker rather than a primary driver.

    Parameters
    ----------
    llm_score        : float in [0.0, 1.0] from signals/llm.py
    stylo_score      : float in [0.0, 1.0] from signals/stylometric.py
    repetition_score : float in [0.0, 1.0] from signals/repetition.py
    word_count       : number of words in the submitted text

    Returns
    -------
    float in [0.0, 1.0] — probability the content is AI-generated.
    """
    if word_count < SHORT_TEXT_THRESHOLD:
        # Below the reliability floor for all three signals: equal weighting,
        # mirroring the conservative approach used in the 2-signal path.
        combined = (
            (1 / 3) * llm_score +
            (1 / 3) * stylo_score +
            (1 / 3) * repetition_score
        )
    else:
        combined = (
            0.50 * llm_score +
            0.30 * stylo_score +
            0.20 * repetition_score
        )

    return round(max(0.0, min(1.0, combined)), 4)


def score_to_verdict(score: float, short_text: bool) -> str:
    """
    Map a combined confidence score to a verdict key.

    Returns one of:
      "high_confidence_ai"
      "high_confidence_human"
      "uncertain"
    """
    if short_text:
        return "uncertain"
    if score >= AI_THRESHOLD:
        return "high_confidence_ai"
    if score <= HUMAN_THRESHOLD:
        return "high_confidence_human"
    return "uncertain"


def generate_label(score: float, short_text: bool) -> str:
    """
    Return the exact display-ready label text for the given score.

    Parameters
    ----------
    score      : combined confidence float in [0.0, 1.0]
    short_text : True if word count < SHORT_TEXT_THRESHOLD
    """
    if short_text:
        return _LABEL_SHORT_TEXT

    if score >= AI_THRESHOLD:
        return _LABEL_AI

    if score <= HUMAN_THRESHOLD:
        return _LABEL_HUMAN

    # Uncertain — embed the numeric score as a percentage
    score_pct = round(score * 100)
    return _LABEL_UNCERTAIN_TEMPLATE.format(score_pct=score_pct)
