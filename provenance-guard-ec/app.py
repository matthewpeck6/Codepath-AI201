"""
app.py — Provenance Guard Flask application (Milestone 5 + Stretch features).

Core endpoints
──────────────
  POST /submit          Accept text or metadata for attribution analysis
  POST /appeal           Contest a classification
  GET  /status/<id>      Look up a content record
  GET  /log              Browse the audit log

Stretch feature endpoints
─────────────────────────
  GET  /verify-human/challenge   Fetch a verification challenge prompt
  POST /verify-human             Submit a response to earn "verified human" status
  GET  /analytics                Detection patterns, appeal rates, confidence stats

Rate limits (on POST /submit)
─────────────────────────────
  10 per hour  per IP
  60 per hour  per IP
  200 per day  per IP

Run
───
  python app.py
"""

import os
import random
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

import db
from scoring import (
    SHORT_TEXT_THRESHOLD,
    compute_confidence_ensemble,
    generate_label,
    score_to_verdict,
)
from signals.llm import SignalError, classify_with_llm
from signals.metadata import classify_metadata
from signals.repetition import classify_repetition
from signals.stylometric import classify_stylometric

# ── App setup ──────────────────────────────────────────────────────────────────

app = Flask(__name__)

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )
    LIMITER_AVAILABLE = True
except ImportError:
    limiter = None
    LIMITER_AVAILABLE = False
    app.logger.warning(
        "flask-limiter is not installed — rate limiting is disabled. "
        "Run: pip install flask-limiter"
    )


def rate_limited(f):
    """Apply submission rate limits when Flask-Limiter is installed."""
    if LIMITER_AVAILABLE:
        return limiter.limit("10 per hour")(
               limiter.limit("60 per hour")(
               limiter.limit("200 per day")(f)))
    return f


db.init_db()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ── POST /submit ───────────────────────────────────────────────────────────────

@app.route("/submit", methods=["POST"])
@rate_limited
def submit():
    """
    Accept content for attribution analysis.

    Request body (text content — default)
    ───────────────────────────────────────
    {
        "text":         "<content to classify>",
        "creator_id":   "<opaque creator identifier>",
        "content_type": "text"            // optional, default "text"
    }

    Request body (metadata content — STRETCH: multi-modal support)
    ─────────────────────────────────────────────────────────────
    {
        "content_type": "metadata",
        "creator_id":   "<opaque creator identifier>",
        "metadata": {
            "camera_model":  "Canon EOS R5" | null,
            "software_used": "Adobe Lightroom" | "Midjourney v6" | null,
            "creation_tool": "Photoshop" | "DALL-E 3" | null,
            "iso":           400 | null,
            "aperture":      "f/2.8" | null
        }
    }

    Response 201
    ────────────
    {
        "content_id":         "<uuid>",
        "attribution":        "high_confidence_ai" | "uncertain" | "high_confidence_human",
        "confidence":         <float 0–1>,
        "label_text":         "<display-ready string>",
        "signals":            { ... one entry per signal that ran ... },
        "short_text_warning": <bool>,
        "signal_error":       <bool>,
        "content_type":       "text" | "metadata",
        "provenance_certificate": { "verified_human": bool, "verified_at": str|null },
        "submitted_at":       "<ISO 8601>"
    }
    """
    body = request.get_json(silent=True)

    if not body:
        return jsonify({"error": "Request body must be JSON."}), 400

    creator_id   = body.get("creator_id", "").strip()
    content_type = (body.get("content_type") or "text").strip().lower()

    if not creator_id:
        return jsonify({"error": "The 'creator_id' field is required."}), 400
    if content_type not in ("text", "metadata"):
        return jsonify({"error": "'content_type' must be 'text' or 'metadata'."}), 400

    content_id   = _new_id()
    entry_id     = _new_id()
    submitted_at = _now_iso()

    # ── Provenance certificate lookup (stretch) ─────────────────────────────────
    verified_record = db.get_verified_creator(creator_id)
    provenance_certificate = {
        "verified_human": verified_record is not None,
        "verified_at": verified_record["verified_at"] if verified_record else None,
    }

    # ════════════════════════════════════════════════════════════════════════════
    # CONTENT TYPE: METADATA  (stretch — multi-modal support)
    # ════════════════════════════════════════════════════════════════════════════
    if content_type == "metadata":
        metadata = body.get("metadata")
        if not isinstance(metadata, dict):
            return jsonify({"error": "'metadata' object is required when content_type is 'metadata'."}), 400

        meta_result = classify_metadata(metadata)
        confidence  = meta_result["score"]
        short_text  = False  # short-text override doesn't apply to metadata
        verdict     = score_to_verdict(confidence, short_text)
        label_text  = generate_label(confidence, short_text)

        db.insert_content(
            content_id      = content_id,
            creator_id      = creator_id,
            submitted_at    = submitted_at,
            verdict         = verdict,
            confidence      = confidence,
            short_text_warn = short_text,
            content_type    = "metadata",
        )

        db.log_decision(
            entry_id          = entry_id,
            content_id        = content_id,
            creator_id        = creator_id,
            timestamp         = submitted_at,
            verdict           = verdict,
            confidence        = confidence,
            llm_score         = None,
            llm_rationale     = None,
            stylo_score       = None,
            stylo_components  = None,
            label_text        = label_text,
            short_text_warn   = short_text,
            signal_error      = False,
            metadata_score      = meta_result["score"],
            metadata_components = meta_result["components"],
            content_type         = "metadata",
        )

        return jsonify({
            "content_id":             content_id,
            "attribution":            verdict,
            "confidence":             confidence,
            "label_text":             label_text,
            "signals":                {"metadata": meta_result},
            "short_text_warning":     short_text,
            "signal_error":           False,
            "content_type":           "metadata",
            "provenance_certificate": provenance_certificate,
            "submitted_at":           submitted_at,
        }), 201

    # ════════════════════════════════════════════════════════════════════════════
    # CONTENT TYPE: TEXT  (default path — ensemble of 3 signals)
    # ════════════════════════════════════════════════════════════════════════════
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "The 'text' field is required and cannot be empty."}), 400
    if len(text) > 50_000:
        return jsonify({"error": "Text exceeds the 50,000 character limit."}), 400

    word_count = len(text.split())
    short_text = word_count < SHORT_TEXT_THRESHOLD

    # ── Signal 1: LLM classifier ──────────────────────────────────────────────
    signal_error = False
    llm_result   = None
    try:
        llm_result = classify_with_llm(text)
    except SignalError as exc:
        app.logger.warning("LLM signal failed for %s: %s", content_id, exc)
        signal_error = True

    # ── Signal 2: Stylometric heuristics ─────────────────────────────────────
    stylo_result = classify_stylometric(text)

    # ── Signal 3: Repetition / predictability heuristic (STRETCH — ensemble) ──
    repetition_result = classify_repetition(text)

    # ── Confidence scoring (ensemble of up to 3 signals) ─────────────────────
    llm_score        = llm_result["score"] if llm_result else None
    stylo_score      = stylo_result["score"]
    repetition_score = repetition_result["score"]

    if llm_score is not None:
        confidence = compute_confidence_ensemble(
            llm_score, stylo_score, repetition_score, word_count
        )
    else:
        # LLM signal failed — fall back to stylometric + repetition, equally weighted
        confidence = round((stylo_score + repetition_score) / 2, 4)

    verdict    = score_to_verdict(confidence, short_text)
    label_text = generate_label(confidence, short_text)

    # ── Persist ───────────────────────────────────────────────────────────────
    db.insert_content(
        content_id      = content_id,
        creator_id      = creator_id,
        submitted_at    = submitted_at,
        verdict         = verdict,
        confidence      = confidence,
        short_text_warn = short_text,
        content_type    = "text",
    )

    db.log_decision(
        entry_id          = entry_id,
        content_id        = content_id,
        creator_id        = creator_id,
        timestamp         = submitted_at,
        verdict           = verdict,
        confidence        = confidence,
        llm_score         = llm_score,
        llm_rationale     = llm_result["rationale"] if llm_result else None,
        stylo_score       = stylo_score,
        stylo_components  = stylo_result.get("components"),
        label_text        = label_text,
        short_text_warn   = short_text,
        signal_error      = signal_error,
        repetition_score      = repetition_score,
        repetition_components = repetition_result.get("components"),
        content_type           = "text",
    )

    # ── Response ──────────────────────────────────────────────────────────────
    signals_out = {
        "stylometric": stylo_result,
        "repetition":  repetition_result,
    }
    if llm_result:
        signals_out["llm"] = llm_result

    return jsonify({
        "content_id":             content_id,
        "attribution":            verdict,
        "confidence":             confidence,
        "label_text":             label_text,
        "signals":                signals_out,
        "short_text_warning":     short_text,
        "signal_error":           signal_error,
        "content_type":           "text",
        "provenance_certificate": provenance_certificate,
        "submitted_at":           submitted_at,
    }), 201


# ── POST /appeal ───────────────────────────────────────────────────────────────

@app.route("/appeal", methods=["POST"])
def appeal():
    """
    Contest a classification.

    Request body
    ────────────
    {
        "content_id":        "<uuid from POST /submit>",
        "creator_id":        "<must match the original submission>",
        "creator_reasoning": "<free text, max 1000 chars>"
    }

    Errors: 400 missing fields · 403 creator mismatch · 404 not found · 409 duplicate
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON."}), 400

    content_id = body.get("content_id", "").strip()
    creator_id = body.get("creator_id", "").strip()
    creator_reasoning = (
        body.get("creator_reasoning") or body.get("reason") or ""
    ).strip()

    if not content_id:
        return jsonify({"error": "'content_id' is required."}), 400
    if not creator_id:
        return jsonify({"error": "'creator_id' is required."}), 400
    if not creator_reasoning:
        return jsonify({"error": "'creator_reasoning' is required."}), 400
    if len(creator_reasoning) > 1000:
        return jsonify({"error": "'creator_reasoning' must be 1000 characters or fewer."}), 400

    record = db.get_content(content_id)
    if not record:
        return jsonify({"error": f"No content found with id '{content_id}'."}), 404

    if record["creator_id"] != creator_id:
        return jsonify({
            "error": "The creator_id does not match the original submission. "
                     "Appeals can only be filed by the original author."
        }), 403

    if record["status"] == "under_review":
        return jsonify({
            "error": "An appeal has already been filed for this content. "
                     "It is currently under review.",
            "content_id": content_id,
            "status": "under_review",
        }), 409

    appeal_id = _new_id()
    logged_at = _now_iso()

    db.set_content_status(content_id, "under_review")

    db.log_appeal(
        entry_id            = appeal_id,
        content_id          = content_id,
        creator_id          = creator_id,
        timestamp           = logged_at,
        original_verdict    = record["verdict"],
        original_confidence = record["confidence"],
        appeal_reason       = creator_reasoning,
    )

    return jsonify({
        "appeal_id":  appeal_id,
        "content_id": content_id,
        "status":     "under_review",
        "message":    (
            "Your appeal has been received and logged. "
            "The content is now marked as under review. "
            "A human reviewer will evaluate your submission alongside the original classification."
        ),
        "logged_at":  logged_at,
    }), 200


# ── GET /status/<content_id> ───────────────────────────────────────────────────

@app.route("/status/<content_id>", methods=["GET"])
def status(content_id: str):
    record = db.get_content(content_id)
    if not record:
        return jsonify({"error": f"No content found with id '{content_id}'."}), 404
    return jsonify(record)


# ── GET /log ───────────────────────────────────────────────────────────────────

@app.route("/log", methods=["GET"])
def log():
    """Return audit log entries as JSON, newest first."""
    type_filter = request.args.get("type")
    creator_id  = request.args.get("creator_id")
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50

    entries = db.get_log(type_filter=type_filter, creator_id=creator_id, limit=limit)
    return jsonify({"count": len(entries), "entries": entries})


# ════════════════════════════════════════════════════════════════════════════════
# STRETCH FEATURE — Provenance certificate ("verified human")
# ════════════════════════════════════════════════════════════════════════════════

_VERIFICATION_CHALLENGES = [
    "Describe, in your own words, why you started writing.",
    "Tell us about a piece of writing — yours or someone else's — that changed how you see something.",
    "Describe your writing process in a few sentences. What does a first draft look like for you?",
    "What is one thing about your own writing style that you find hard to change?",
]

# Trivial / templated responses that should NOT pass the lightweight check.
_TRIVIAL_RESPONSES = {"n/a", "na", "none", "test", "asdf", "...", "idk"}


@app.route("/verify-human/challenge", methods=["GET"])
def verify_human_challenge():
    """
    [STRETCH FEATURE — Provenance certificate]
    Return a randomly chosen verification challenge prompt.
    """
    return jsonify({"challenge": random.choice(_VERIFICATION_CHALLENGES)})


@app.route("/verify-human", methods=["POST"])
def verify_human():
    """
    [STRETCH FEATURE — Provenance certificate]

    Submit a freeform response to earn "verified human" status.

    This is a lightweight credential, NOT robust identity verification.
    It filters out trivially empty/templated responses; it does not (and
    cannot, in this implementation) prove the responder is human rather
    than an LLM. Documented honestly in README § Known limitations.

    Request body
    ────────────
    { "creator_id": "...", "response_text": "..." }

    Response 200
    ────────────
    { "creator_id": "...", "verified_human": true, "verified_at": "..." }

    Response 422 — response failed the basic non-triviality check
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON."}), 400

    creator_id    = body.get("creator_id", "").strip()
    response_text = body.get("response_text", "").strip()

    if not creator_id:
        return jsonify({"error": "'creator_id' is required."}), 400
    if not response_text:
        return jsonify({"error": "'response_text' is required."}), 400

    normalized = response_text.lower().strip(".! ")
    word_count = len(response_text.split())

    if normalized in _TRIVIAL_RESPONSES or word_count < 8:
        return jsonify({
            "error": "Response is too short or appears templated. "
                     "Please write a few genuine sentences to complete verification.",
            "verified_human": False,
        }), 422

    verified_at = _now_iso()
    db.mark_creator_verified(creator_id, verified_at)

    return jsonify({
        "creator_id":     creator_id,
        "verified_human": True,
        "verified_at":    verified_at,
    }), 200


# ════════════════════════════════════════════════════════════════════════════════
# STRETCH FEATURE — Analytics dashboard
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/analytics", methods=["GET"])
def analytics():
    """
    [STRETCH FEATURE — Analytics dashboard]

    Aggregate audit log data: verdict distribution, appeal rate (overall
    and by verdict), and average confidence by verdict bucket.

    All figures are computed live from the audit_log table — no separate
    analytics storage.
    """
    return jsonify(db.get_analytics())


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
