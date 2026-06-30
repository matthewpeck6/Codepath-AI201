"""
db.py — SQLite database layer for Provenance Guard.

Handles:
  - Schema creation on startup
  - Writing decision and appeal audit log entries
  - Reading log entries with optional filters
  - Content record status updates
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "provenance.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection with row_factory set so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS content (
                content_id      TEXT PRIMARY KEY,
                creator_id      TEXT NOT NULL,
                submitted_at    TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'classified',
                verdict         TEXT,
                confidence      REAL,
                short_text_warn INTEGER NOT NULL DEFAULT 0,
                content_type    TEXT NOT NULL DEFAULT 'text'
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id                  TEXT PRIMARY KEY,
                type                TEXT NOT NULL,
                content_id          TEXT NOT NULL,
                creator_id          TEXT NOT NULL,
                timestamp           TEXT NOT NULL,
                verdict             TEXT,
                confidence          REAL,
                llm_score           REAL,
                llm_rationale       TEXT,
                stylo_score         REAL,
                stylo_components    TEXT,
                repetition_score    REAL,
                repetition_components TEXT,
                metadata_score      REAL,
                metadata_components TEXT,
                content_type        TEXT NOT NULL DEFAULT 'text',
                label_text          TEXT,
                appeal_reason       TEXT,
                status              TEXT,
                short_text_warn     INTEGER NOT NULL DEFAULT 0,
                signal_error        INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS verified_creators (
                creator_id   TEXT PRIMARY KEY,
                verified_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_content ON audit_log(content_id);
            CREATE INDEX IF NOT EXISTS idx_audit_type    ON audit_log(type);
            CREATE INDEX IF NOT EXISTS idx_audit_creator ON audit_log(creator_id);
        """)
        # Best-effort migration for DBs created before these columns existed.
        _ensure_column(conn, "content", "content_type", "TEXT NOT NULL DEFAULT 'text'")
        for col, decl in [
            ("repetition_score",      "REAL"),
            ("repetition_components", "TEXT"),
            ("metadata_score",        "REAL"),
            ("metadata_components",   "TEXT"),
            ("content_type",          "TEXT NOT NULL DEFAULT 'text'"),
        ]:
            _ensure_column(conn, "audit_log", col, decl)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Add `column` to `table` if it doesn't already exist (lightweight migration)."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# ── Content records ────────────────────────────────────────────────────────────

def insert_content(content_id: str, creator_id: str, submitted_at: str,
                   verdict: str, confidence: float, short_text_warn: bool,
                   content_type: str = "text") -> None:
    """Insert a new content record when a submission is first classified."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO content
               (content_id, creator_id, submitted_at, status, verdict,
                confidence, short_text_warn, content_type)
               VALUES (?, ?, ?, 'classified', ?, ?, ?, ?)""",
            (content_id, creator_id, submitted_at, verdict,
             round(confidence, 4), int(short_text_warn), content_type)
        )


def get_content(content_id: str) -> dict | None:
    """Return a content record as a dict, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM content WHERE content_id = ?", (content_id,)
        ).fetchone()
    return dict(row) if row else None


def set_content_status(content_id: str, status: str) -> None:
    """Update the status field on a content record."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE content SET status = ? WHERE content_id = ?",
            (status, content_id)
        )


# ── Audit log ──────────────────────────────────────────────────────────────────

def log_decision(
    *,
    entry_id: str,
    content_id: str,
    creator_id: str,
    timestamp: str,
    verdict: str,
    confidence: float,
    llm_score: float | None,
    llm_rationale: str | None,
    stylo_score: float | None,
    stylo_components: dict | None,
    label_text: str,
    short_text_warn: bool,
    signal_error: bool,
    repetition_score: float | None = None,
    repetition_components: dict | None = None,
    metadata_score: float | None = None,
    metadata_components: dict | None = None,
    content_type: str = "text",
) -> None:
    """Write a 'decision' entry to the audit log."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (id, type, content_id, creator_id, timestamp,
                verdict, confidence, llm_score, llm_rationale,
                stylo_score, stylo_components,
                repetition_score, repetition_components,
                metadata_score, metadata_components,
                content_type, label_text,
                status, short_text_warn, signal_error)
               VALUES (?, 'decision', ?, ?, ?,
                       ?, ?, ?, ?,
                       ?, ?,
                       ?, ?,
                       ?, ?,
                       ?, ?,
                       'classified', ?, ?)""",
            (
                entry_id, content_id, creator_id, timestamp,
                verdict, round(confidence, 4),
                round(llm_score, 4) if llm_score is not None else None,
                llm_rationale,
                round(stylo_score, 4) if stylo_score is not None else None,
                json.dumps(stylo_components) if stylo_components else None,
                round(repetition_score, 4) if repetition_score is not None else None,
                json.dumps(repetition_components) if repetition_components else None,
                round(metadata_score, 4) if metadata_score is not None else None,
                json.dumps(metadata_components) if metadata_components else None,
                content_type,
                label_text,
                int(short_text_warn), int(signal_error),
            )
        )


def log_appeal(
    *,
    entry_id: str,
    content_id: str,
    creator_id: str,
    timestamp: str,
    original_verdict: str,
    original_confidence: float,
    appeal_reason: str,
) -> None:
    """Write an 'appeal' entry to the audit log."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (id, type, content_id, creator_id, timestamp,
                verdict, confidence, appeal_reason, status)
               VALUES (?, 'appeal', ?, ?, ?,
                       ?, ?, ?, 'under_review')""",
            (
                entry_id, content_id, creator_id, timestamp,
                original_verdict, round(original_confidence, 4),
                appeal_reason,
            )
        )


def get_log(*, type_filter: str | None = None,
            creator_id: str | None = None,
            limit: int = 50) -> list[dict]:
    """
    Return audit log entries as a list of dicts, newest first.
    Optional filters: type ('decision' | 'appeal'), creator_id.
    """
    clauses = []
    params: list = []

    if type_filter:
        clauses.append("type = ?")
        params.append(type_filter)
    if creator_id:
        clauses.append("creator_id = ?")
        params.append(creator_id)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(max(1, min(limit, 200)))  # cap at 200

    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ?",
            params
        ).fetchall()

    results = []
    for row in rows:
        entry = dict(row)
        # Parse the JSON blobs back to dicts for clean API output
        for json_field in ("stylo_components", "repetition_components", "metadata_components"):
            if entry.get(json_field):
                try:
                    entry[json_field] = json.loads(entry[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # Convert SQLite integers back to booleans
        entry["short_text_warn"] = bool(entry.get("short_text_warn", 0))
        entry["signal_error"] = bool(entry.get("signal_error", 0))
        results.append(entry)

    return results


# ── Verified creators (provenance certificate) ──────────────────────────────────

def mark_creator_verified(creator_id: str, verified_at: str) -> None:
    """Insert or update a creator's verified-human status."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO verified_creators (creator_id, verified_at)
               VALUES (?, ?)
               ON CONFLICT(creator_id) DO UPDATE SET verified_at = excluded.verified_at""",
            (creator_id, verified_at)
        )


def get_verified_creator(creator_id: str) -> dict | None:
    """Return {'creator_id', 'verified_at'} if the creator is verified, else None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM verified_creators WHERE creator_id = ?", (creator_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Analytics ──────────────────────────────────────────────────────────────────

def get_analytics() -> dict:
    """
    Aggregate audit log data into summary statistics.

    Returns
    -------
    {
        "total_decisions": int,
        "verdict_distribution": {
            "high_confidence_ai":    {"count": int, "pct": float},
            "uncertain":             {"count": int, "pct": float},
            "high_confidence_human": {"count": int, "pct": float},
        },
        "total_appeals": int,
        "appeal_rate": float,                       # appeals / total_decisions
        "appeal_rate_by_verdict": {
            "<verdict>": float, ...
        },
        "avg_confidence_by_verdict": {
            "<verdict>": float, ...
        }
    }
    """
    with get_connection() as conn:
        total_decisions = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE type = 'decision'"
        ).fetchone()["n"]

        verdict_rows = conn.execute(
            """SELECT verdict, COUNT(*) AS n, AVG(confidence) AS avg_conf
               FROM audit_log
               WHERE type = 'decision' AND verdict IS NOT NULL
               GROUP BY verdict"""
        ).fetchall()

        total_appeals = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE type = 'appeal'"
        ).fetchone()["n"]

        appeals_by_verdict_rows = conn.execute(
            """SELECT verdict, COUNT(*) AS n
               FROM audit_log
               WHERE type = 'appeal' AND verdict IS NOT NULL
               GROUP BY verdict"""
        ).fetchall()

    verdict_distribution = {}
    avg_confidence_by_verdict = {}
    decision_counts_by_verdict = {}

    for row in verdict_rows:
        v = row["verdict"]
        n = row["n"]
        decision_counts_by_verdict[v] = n
        pct = round((n / total_decisions) * 100, 2) if total_decisions else 0.0
        verdict_distribution[v] = {"count": n, "pct": pct}
        avg_confidence_by_verdict[v] = round(row["avg_conf"], 4) if row["avg_conf"] is not None else None

    appeals_by_verdict = {row["verdict"]: row["n"] for row in appeals_by_verdict_rows}

    appeal_rate_by_verdict = {}
    for verdict, decision_count in decision_counts_by_verdict.items():
        appeal_count = appeals_by_verdict.get(verdict, 0)
        appeal_rate_by_verdict[verdict] = (
            round(appeal_count / decision_count, 4) if decision_count else 0.0
        )

    overall_appeal_rate = (
        round(total_appeals / total_decisions, 4) if total_decisions else 0.0
    )

    return {
        "total_decisions": total_decisions,
        "verdict_distribution": verdict_distribution,
        "total_appeals": total_appeals,
        "appeal_rate": overall_appeal_rate,
        "appeal_rate_by_verdict": appeal_rate_by_verdict,
        "avg_confidence_by_verdict": avg_confidence_by_verdict,
    }
