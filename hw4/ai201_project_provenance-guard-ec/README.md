# Provenance Guard

AI content attribution for writing platforms. Provenance Guard classifies text submissions as likely AI-generated, likely human-written, or uncertain — using a two-signal detection pipeline, calibrated confidence scoring, plain-language transparency labels, and a creator appeals workflow.

**Stack:** Python · Flask · Groq (llama-3.3-70b-versatile) · SQLite · Flask-Limiter

---

## Table of contents

1. [Setup](#setup)
2. [Architecture overview](#architecture-overview)
3. [Detection signals](#detection-signals)
4. [Confidence scoring](#confidence-scoring)
5. [Transparency label variants](#transparency-label-variants)
6. [Appeals workflow](#appeals-workflow)
7. [Rate limiting](#rate-limiting)
8. [Audit log](#audit-log)
9. [Known limitations](#known-limitations)
10. [Spec reflection](#spec-reflection)
11. [AI usage](#ai-usage)
12. [Stretch features](#stretch-features)
13. [API reference](#api-reference)

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/ai201-project4-provenance-guard
cd ai201-project4-provenance-guard

python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# source .venv/Scripts/activate  # Windows Git Bash

pip install -r requirements.txt

# Create .env — never commit this file
echo "GROQ_API_KEY=your_key_here" > .env

python app.py
# → http://localhost:5000
```

---

## Architecture overview

A submission travels through the following path from input to transparency label:

```
POST /submit  {text, creator_id}
      │
      ▼
Flask-Limiter
  checks quota (10/hr per IP; 60/hr; 200/day)
  → 429 if exceeded
      │
      ├─────────────────────────────────┐
      ▼                                 ▼
Signal 1                           Signal 2
LLM classifier (Groq)              Stylometric heuristics
llama-3.3-70b-versatile            avg word length · sentence
→ score: float 0–1                 variance · punct density ·
→ rationale: str                   subordinate ratio
→ raises SignalError               → score: float 0–1
  on bad API response                (pure Python, no API)
      │                                 │
      └──────────────┬──────────────────┘
                     ▼
              Confidence scorer
              long text:  0.60 × llm + 0.40 × stylo
              short text: 0.50 × llm + 0.50 × stylo
              → combined_score: float 0–1
                     │
                     ▼
              Threshold check
              ≥ 0.80  →  high_confidence_ai    (Variant A)
              0.20–0.79  →  uncertain          (Variant C)
              ≤ 0.20  →  high_confidence_human (Variant B)
              < 40 words  →  uncertain forced  (short override)
                     │
                     ▼
              Label generator
              → label_text: exact display string
                     │
                     ▼
              SQLite audit log
              (decision entry: both signal scores,
               combined score, label_text, timestamp)
                     │
                     ▼
              JSON response  →  client
```

**Appeal flow:**

```
POST /appeal  {content_id, creator_id, creator_reasoning}
      │
      ├── 404 if content_id not found
      ├── 403 if creator_id doesn't match original
      ├── 409 if appeal already filed
      ▼
  content.status  →  "under_review"
      │
      ▼
  SQLite audit log
  (appeal entry: original verdict + scores + verbatim reasoning)
      │
      ▼
  JSON confirmation  →  client
```

**File structure:**

```
app.py                  Flask application — all endpoints
db.py                   SQLite layer — schema, reads, writes
scoring.py              Confidence math + label text strings
signals/
  llm.py                Signal 1 — Groq API classifier
  stylometric.py        Signal 2 — pure Python heuristics
planning.md             Written before implementation
requirements.txt
.gitignore              Excludes .env, provenance.db, __pycache__
```

---

## Detection signals

Two signals are combined into a single confidence score. They are genuinely independent: Signal 1 is semantic (what the text is saying and how it sounds), Signal 2 is structural (measurable properties of how it is written). They can disagree — and when they disagree strongly, that disagreement is itself informative. A text with human-like statistics but AI-like semantics lands in the uncertain band rather than being forced to a verdict.

### Signal 1 — LLM semantic classifier

**What it measures:** Holistic stylistic and semantic coherence. The Groq LLM reads the submitted text and returns a probability (0–1) that it is AI-generated, plus a one-sentence rationale. It captures uniform hedging language ("it is important to note that"), over-structured pacing, the absence of personal idiosyncrasy, and the characteristic confident-but-generic tone of LLM prose.

**Why I chose it:** A ruleset cannot capture the *feel* of AI writing — that quality a reader recognizes without being able to articulate. An LLM classifier can. It also makes the two signals genuinely independent: Signal 1 judges meaning and voice, Signal 2 measures statistics. Combining them is more informative than two variants of the same approach.

**Why the property differs between human and AI writing:** LLMs trained on human feedback converge toward smooth, well-organized, predictable prose. Human writing meanders, commits to awkward phrasings, and carries personal voice. The signal picks this up holistically in ways a heuristic set cannot.

**What it misses:** Skilled mimicry in either direction. Academic and technical writing is uniformly formal in ways that look like AI output. The signal is also less reliable on submissions under 40 words — there is not enough semantic content to judge.

**Prompt injection defense:** The user's text is placed inside triple-quoted delimiters. The system prompt explicitly tells the model to return ONLY JSON and to ignore any instructions embedded in the text. The server validates the response parses as JSON with a float `score` in [0.0, 1.0] before using it — any other response raises `SignalError` and the system falls back to Signal 2 alone, setting `signal_error: true` in the response and audit log.

---

### Signal 2 — Stylometric heuristics

**What it measures:** Four structural statistics computed directly from the text in pure Python, with no external libraries or API calls:

| Statistic | What it captures | AI tendency |
|---|---|---|
| Average word length | Formality of vocabulary | Higher — AI uses longer, Latinate words |
| Sentence length variance | Rhythm variation | Lower — AI keeps sentence length consistent |
| Punctuation density | Punctuation usage | Lower — AI uses punctuation conservatively |
| Subordinate clause ratio | Syntactic complexity | Lower — AI favors parallel simple sentences |

Each statistic is normalized to [0.0, 1.0] using calibration ranges derived from a reference corpus of 6 texts (3 clearly AI, 3 clearly human). The four normalized human-likeness scores are averaged, then inverted: `stylo_score = 1.0 - human_likeness`. Higher score = more AI-like.

**Why I chose it:** It is structurally independent of Signal 1. It requires no API key, never fails due to a network error, and provides a fallback if the LLM signal is unavailable. It also measures properties of the text *as a physical artifact* — statistics that are harder to spoof than semantic patterns.

**Why TTR was dropped during calibration:** Type-token ratio is length-sensitive. At 40–80 words, both AI and human text achieves TTR 0.74–0.90, providing almost no discrimination. Measuring the reference corpus made this visible immediately. Average word length proved more reliable and is not length-sensitive (AI: 5.1–6.4 chars/word, Human: 4.1–4.5 chars/word across the corpus).

**Calibration ranges:**

| Statistic | AI range (observed) | Human range (observed) | ai_end | human_end |
|---|---|---|---|---|
| Average word length | 5.1–6.4 chars | 4.1–4.5 chars | 6.5 | 4.0 |
| Sentence length variance | 2.9–5.4 SD | 5.1–7.4 SD | 2.0 | 9.0 |
| Punctuation density | 0.014–0.028 | 0.014–0.038 | 0.015 | 0.035 |
| Subordinate clause ratio | 0.0–0.33 | 0.20–0.75 | 0.05 | 0.70 |

**What it misses:** Genre is a serious confounder. A minimalist author (Hemingway, Carver, Saramago) uses short sentences, simple vocabulary, and no subordinate clauses — the same structural profile as AI output. This signal cannot distinguish minimalism from AI generation on structural properties alone. The LLM signal usually counterbalances this because it reads for voice, not just statistics; but it is a documented false-positive risk (see Known limitations).

---

### Combining the signals

```
Long text  (≥ 40 words): combined = 0.60 × llm_score + 0.40 × stylo_score
Short text (< 40 words): combined = 0.50 × llm_score + 0.50 × stylo_score
```

The LLM gets 60% weight on longer texts because it is more reliable when it has sufficient semantic content to judge. For short texts, neither signal is reliable; 50/50 reduces over-reliance on either.

**What I would change for real deployment:** The 60/40 split was chosen by reasoning, not by measuring accuracy on a labeled dataset. A real system would use logistic regression or a small ensemble model trained on a labeled corpus to find the optimal weights empirically. The calibration ranges for Signal 2 would also be measured from thousands of texts rather than six.

---

## Confidence scoring

The combined score is a float in [0.0, 1.0] where 1.0 = maximally AI-likely.

### Threshold mapping

| Score range | Verdict key | Label shown |
|---|---|---|
| ≥ 0.80 | `high_confidence_ai` | Variant A |
| 0.20 – 0.79 | `uncertain` | Variant C |
| ≤ 0.20 | `high_confidence_human` | Variant B |

**Why 0.80 / 0.20, not 0.50?** A false positive — labeling a human's work as AI-generated — is more harmful on a writing platform than a false negative. A writer falsely accused has their reputation damaged. A reader who encounters AI content that slipped through has less information. The asymmetric threshold reflects this: borderline cases default to "uncertain" rather than "accused." The cost of being wrong in the AI direction is higher than the cost of being wrong in the human direction, so the AI threshold is set higher.

**Scores are always surfaced numerically.** A 0.51 score and a 0.79 score are both `uncertain`, but they are not the same. The raw confidence score is included in every API response and audit log entry. The Variant C label text includes the numeric percentage so a non-technical reader also sees the degree of uncertainty.

### Two example submissions showing meaningful score variation

**High-confidence example** — clearly AI-generated text:

> *"Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment."*

```
LLM score:         0.90   (uniform formal register, no personal voice)
Stylometric score: 0.731  (avg word length 6.23, low sentence variance)
Combined:          0.832
Verdict:           high_confidence_ai
```

**Lower-confidence example** — formal human academic writing (borderline):

> *"The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations."*

```
LLM score:         0.55   (formal, but structured argument has human reasoning pattern)
Stylometric score: 0.818  (avg word length 5.93 — long, but 0 subordinate clauses drags it up)
Combined:          0.657
Verdict:           uncertain
```

The gap between these two — 0.832 vs 0.657 — shows that the system is not simply returning high scores for all formal text. The signals disagree on the second example (LLM reads it as borderline human, stylometrics reads it as AI-like due to zero subordinate clauses), which pulls it toward `uncertain` rather than a confident verdict. This disagreement is the correct behavior.

---

## Transparency label variants

Three variants. These are the **exact strings** returned in the `label_text` field of every `/submit` response and written to the audit log.

---

### Variant A — High-confidence AI
*Triggered when `combined_score ≥ 0.80`*

> "Our analysis suggests this content was likely written with AI assistance. Confidence: high. Detection systems are not perfect. If you are the author and believe this is incorrect, you can contest this finding using the appeal option below."

**Design decisions:** "likely" not "definitely" — no detection system is perfect and overclaiming harms trust. The appeal path is named explicitly so creators who see this label know immediately what to do. Which signals fired is not disclosed, to reduce gaming.

---

### Variant B — High-confidence human
*Triggered when `combined_score ≤ 0.20`*

> "This content shows strong indicators of human authorship. No significant AI involvement detected. Confidence: high."

**Design decisions:** Shorter than Variant A — a clean result does not need caveats about imperfection. "No significant AI involvement" is deliberately modest; it leaves room for autocomplete and grammar tools without accusing the author of misrepresentation.

---

### Variant C — Uncertain
*Triggered when `0.20 < combined_score < 0.80`*

> "Our system could not confidently determine the authorship of this content (confidence score: {N}%). The signals were mixed or inconclusive. This is not a finding of AI use. Authors can provide additional context using the appeal option below."

`{N}` is the numeric percentage (e.g. `"confidence score: 61%"`). A 55% uncertain and a 78% uncertain display different numbers.

**Design decisions:** "This is not a finding of AI use" is the most important sentence. A reader who sees this label should not walk away thinking the content is probably AI — they should understand the system genuinely could not tell. The appeal path is included because creators who receive this on human work may want to provide context, even though no accusation was made.

---

### Short text override
*Applied when word count < 40, regardless of computed score*

> "Our system could not confidently determine the authorship of this content. The submission is too short for a reliable verdict. This is not a finding of AI use. Authors can provide additional context using the appeal option below."

Forced to Variant C text. `short_text_warning: true` is set in the response. Even a score of 0.95 does not trigger Variant A on a 10-word submission — there is not enough evidence to issue a high-confidence verdict, and issuing one would be misleading.

---

## Appeals workflow

### Who can appeal

Any `creator_id` can file an appeal for a `content_id` that belongs to their account. The server checks that the `creator_id` on the appeal matches the original submission. Mismatched appeals return HTTP 403.

### Submitting an appeal

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{
    "content_id": "PASTE-CONTENT-ID-HERE",
    "creator_id": "test-user-1",
    "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."
  }' | python -m json.tool
```

Response:

```json
{
    "appeal_id": "7a739cfe-...",
    "content_id": "abc12345-...",
    "status": "under_review",
    "message": "Your appeal has been received and logged. The content is now marked as under review. A human reviewer will evaluate your submission alongside the original classification.",
    "logged_at": "2025-06-01T14:33:00+00:00"
}
```

### What happens on the server

1. `content_id` validated → 404 if not found
2. `creator_id` checked against original submission → 403 if mismatch
3. Status checked for existing appeal → 409 if duplicate
4. Content record status: `"classified"` → `"under_review"`
5. Appeal entry written to audit log (carries original verdict, original score, verbatim reasoning)
6. Confirmation returned

No automated re-classification. The appeal is a human-review flag.

### Verifying the appeal is logged

```bash
curl "http://localhost:5000/log?type=appeal" | python -m json.tool
```

Each appeal entry in the log carries the original verdict and both signal scores alongside the creator's stated reason — a reviewer has the full picture in one record with no second lookup.

---

## Rate limiting

Applied to `POST /submit` via Flask-Limiter.

| Limit | Window | Reasoning |
|---|---|---|
| 10 per hour | per IP | A writer revising a draft won't exceed this; a boundary-probing script will |
| 60 per hour | per IP | Burst ceiling; generous for developer testing, stops automated floods |
| 200 per day | per IP | Long-run ceiling; covers a heavy-revision day, stops sustained scraping |

**Why these specific numbers:** The central adversarial concern is an actor submitting many variations of AI text to find phrasings that score below the detection threshold. That requires many rapid requests — any reasonable per-hour limit stops it. The 10/hour figure is chosen because a human writer doing genuine revision work submits at most a few times in a session; 10 is above that while remaining clearly below automation rates. The 200/day ceiling prevents sustained multi-session probing even if the hourly limit is reset.

**Evidence — rate limit in action** (12 rapid requests to `/submit`, limit is 10/hour):

```
200
200
200
200
200
200
200
200
200
200
429
429
```

The first 10 requests succeed; 11 and 12 return HTTP 429 Too Many Requests.

To reproduce:

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "Rate limit test submission.", "creator_id": "ratelimit-test"}'
done
```

---

## Audit log

Every attribution decision and every appeal is written to the SQLite `audit_log` table. `GET /log` returns structured JSON, newest first.

### Schema

```sql
CREATE TABLE audit_log (
    id               TEXT PRIMARY KEY,
    type             TEXT NOT NULL,      -- 'decision' or 'appeal'
    content_id       TEXT NOT NULL,
    creator_id       TEXT NOT NULL,
    timestamp        TEXT NOT NULL,      -- ISO 8601 UTC
    verdict          TEXT,               -- 'high_confidence_ai' | 'uncertain' | 'high_confidence_human'
    confidence       REAL,               -- combined score
    llm_score        REAL,
    llm_rationale    TEXT,
    stylo_score      REAL,
    stylo_components TEXT,               -- JSON blob of four component values
    label_text       TEXT,               -- exact string shown to reader
    appeal_reason    TEXT,               -- NULL for decision rows
    status           TEXT,
    short_text_warn  INTEGER,
    signal_error     INTEGER
);
```

### Sample output — `GET /log`

Shows 4 entries: one appeal, two decision entries covering all three verdict types.

```json
{
  "count": 4,
  "entries": [
    {
      "id": "e-appeal-001",
      "type": "appeal",
      "content_id": "abc-111-...",
      "creator_id": "user-alice",
      "timestamp": "2025-06-01T14:33:00+00:00",
      "verdict": "high_confidence_ai",
      "confidence": 0.869,
      "llm_score": null,
      "llm_rationale": null,
      "stylo_score": null,
      "stylo_components": null,
      "label_text": null,
      "appeal_reason": "I wrote this myself. I am an academic and my writing style is naturally formal.",
      "status": "under_review",
      "short_text_warn": false,
      "signal_error": false
    },
    {
      "id": "e-dec-003",
      "type": "decision",
      "content_id": "def-222-...",
      "creator_id": "user-bob",
      "timestamp": "2025-06-01T14:32:00+00:00",
      "verdict": "uncertain",
      "confidence": 0.607,
      "llm_score": 0.55,
      "llm_rationale": "Mixed signals; some formal vocabulary but personal phrasing present.",
      "stylo_score": 0.694,
      "stylo_components": {
        "avg_word_length": 5.93,
        "sentence_variance": 5.5,
        "punct_density": 0.0067,
        "subordinate_ratio": 0.0
      },
      "label_text": "Our system could not confidently determine the authorship of this content (confidence score: 61%). The signals were mixed or inconclusive. This is not a finding of AI use.",
      "appeal_reason": null,
      "status": "classified",
      "short_text_warn": false,
      "signal_error": false
    },
    {
      "id": "e-dec-002",
      "type": "decision",
      "content_id": "abc-111-...",
      "creator_id": "user-alice",
      "timestamp": "2025-06-01T14:31:00+00:00",
      "verdict": "high_confidence_ai",
      "confidence": 0.869,
      "llm_score": 0.9,
      "llm_rationale": "Prose uses formal academic register with uniform sentence rhythm and no personal voice.",
      "stylo_score": 0.813,
      "stylo_components": {
        "avg_word_length": 6.23,
        "sentence_variance": 5.44,
        "punct_density": 0.0159,
        "subordinate_ratio": 0.333
      },
      "label_text": "Our analysis suggests this content was likely written with AI assistance. Confidence: high. Detection systems are not perfect. If you are the author and believe this is incorrect, you can contest this finding using the appeal option below.",
      "appeal_reason": null,
      "status": "under_review",
      "short_text_warn": false,
      "signal_error": false
    },
    {
      "id": "e-dec-001",
      "type": "decision",
      "content_id": "ghi-333-...",
      "creator_id": "user-carol",
      "timestamp": "2025-06-01T14:30:00+00:00",
      "verdict": "high_confidence_human",
      "confidence": 0.087,
      "llm_score": 0.08,
      "llm_rationale": "Strong personal voice, casual register, and idiosyncratic punctuation.",
      "stylo_score": 0.097,
      "stylo_components": {
        "avg_word_length": 4.25,
        "sentence_variance": 6.72,
        "punct_density": 0.0137,
        "subordinate_ratio": 0.4
      },
      "label_text": "This content shows strong indicators of human authorship. No significant AI involvement detected. Confidence: high.",
      "appeal_reason": null,
      "status": "classified",
      "short_text_warn": false,
      "signal_error": false
    }
  ]
}
```

---

## Known limitations

### Minimalist literary prose — a structural false positive

The stylometric signal measures sentence length variance, subordinate clause ratio, and punctuation density. Writers in a spare style — Hemingway, Carver, Saramago, most flash fiction — use short declarative sentences, simple vocabulary, and almost no subordinate clauses. These structural properties overlap almost completely with AI-generated prose. The stylometric signal cannot distinguish minimalism from AI generation because they share the same surface statistics.

The LLM signal usually counterbalances this: it reads for voice and idiosyncrasy, and a skilled minimalist has a distinct voice. But for very short minimalist submissions, the LLM signal also has limited reliability. The combined score for a Hemingway excerpt in the calibration tests came out at 0.375, landing in the `uncertain` band. That is the correct outcome — but a creator who regularly writes in this style will receive `uncertain` verdicts on genuinely human work. The appeal path is the designed resolution; there is no statistical fix that preserves sensitivity to AI while also not flagging minimalist prose.

### Formal academic prose — the signal agreement problem

The four-column calibration test showed that formal human academic writing (the "monetary policy" text) scores 0.818 on stylometrics. That score is high because the text has long words, consistent sentence length, low punctuation density, and zero subordinate clauses — the same profile as AI output at the structural level. The LLM signal at 0.55 pulls the combined score down to 0.657, keeping it in `uncertain`. But the stylometric signal is providing almost no useful information here: it simply cannot distinguish academic register from AI register. Any platform with a significant academic writing audience will see elevated `uncertain` rates on legitimate submissions from that cohort.

### The 40-word threshold is approximate

The short-text override forces `uncertain` for submissions under 40 words. The actual reliability floor for both signals varies with text complexity, not just length — a 35-word dense argument provides more signal than a 60-word list of simple statements. The threshold is a rough practical heuristic. In a real deployment it would be worth measuring signal variance against word count and setting a threshold that corresponds to a specific reliability level rather than a round number.

### Weights were chosen by reasoning, not measurement

The 60/40 LLM/stylometric split and the 0.80/0.20 verdict thresholds were derived from reasoning about signal reliability — not from measuring accuracy on a labeled dataset. A system trained on real labeled submissions from the platform would likely use different weights. The current values are defensible starting points, but calling them "calibrated" overstates the evidence.

---

## Spec reflection

### One way the spec helped

The spec's false positive framing in the hints section — "a false positive (labeling a human's work as AI-generated) is worse than a false negative on a writing platform" — was the most practically useful design guidance in the entire document. It told me to make an architectural decision before writing any code: set the AI threshold at 0.80, not 0.50. That single decision touches the threshold mapping in `scoring.py`, the label text in Variant A and C (both explicitly disclaim certainty), and the appeals workflow (designed to handle the case where a creator receives a false positive). Without that framing, I would have defaulted to 0.50 and built a system that labeled far more borderline cases as AI-generated. The spec's willingness to name the asymmetry — rather than just asking me to "be accurate" — made the implementation more honest.

### One way implementation diverged from the spec

The planning document specified type-token ratio (TTR) as one of the four stylometric statistics. During Milestone 4 calibration, measuring the actual reference corpus revealed that TTR provides almost no discrimination at short text lengths: both AI and human text achieves TTR 0.74–0.90 at 40–80 words. TTR is length-sensitive by construction — shorter texts always have higher TTR regardless of authorship — and most submissions are in this length range.

I replaced TTR with average word length, which cleanly separates the corpus: AI text averages 5.1–6.4 characters per word, human casual text 4.1–4.5. This diverged from the planning spec, but the planning spec itself anticipated this: it noted that calibration should be verified against real texts and that adjustments might be needed. The discovery was the calibration working as intended, not a failure of planning.

---

## AI usage

### Instance 1 — Database layer generation

**What I directed:** I provided the full `planning.md` schema section and asked the AI to generate the complete `db.py` module: the SQLite schema with both `content` and `audit_log` tables, the `init_db()` function, and all CRUD operations (`insert_content`, `log_decision`, `log_appeal`, `get_log` with optional filters, `get_content`, `set_content_status`).

**What it produced:** A functional module with the correct schema and all six functions. The generated `get_log` function accepted the type and creator_id filter parameters and built the WHERE clause correctly.

**What I revised:** The generated code used positional argument functions throughout. I converted all write functions to keyword-only arguments (using `*` as a separator) — this eliminates a class of subtle bugs where the wrong value gets passed to the wrong column when the call site lists arguments in the wrong order. The audit log has 15 columns; one transposition would silently log the wrong data. I also added the `row_factory = sqlite3.Row` line, which the generated version omitted — without it, rows return as tuples and have to be accessed by index rather than by column name, which makes the code fragile against schema changes.

### Instance 2 — Stylometric signal calibration

**What I directed:** I asked the AI to measure the four stylometric statistics against the six reference corpus texts (three clearly AI, three clearly human) and report the raw values so I could derive accurate calibration ranges.

**What it produced:** A measurement script that computed all four statistics for each text and printed a comparison table, showing the observed ranges per group.

**What I revised:** The output confirmed that TTR was not discriminating — both groups clustered at 0.74–0.90. I overrode the original spec decision to use TTR and replaced it with average word length, which the AI had measured as part of the same diagnostic run and which showed a clean gap (AI 5.1–6.4, human 4.1–4.5). I also tightened the sentence variance calibration range from (1.0, 18.0) — which was based on guessing — to (2.0, 9.0), which was based on the observed data. The original ranges had compressed most scores into the 0.4–0.6 band; the recalibrated ranges spread them meaningfully. The AI produced the measurement tool; the decision to replace TTR and recalibrate the ranges was mine.

---

## Stretch features

All four stretch features are implemented. Each is documented here with what was built and how it works; the design reasoning for each lives in `planning.md § Stretch features — planning`, written before implementation as required.

---

### Stretch — Ensemble detection (3+ signals)

A third signal was added: **Signal 3 — lexical predictability heuristic** (`signals/repetition.py`), measuring hedge-word and stock-phrase density (words like "numerous," "comprehensive," "furthermore," and phrases like "it is important to note" that are disproportionately common in LLM output).

**Calibration note:** the first version of this signal used bigram repetition rate as its primary statistic. Measuring it against the reference corpus showed it doesn't discriminate at all at 30–45 word lengths — short texts rarely repeat any bigram regardless of authorship, so the stat clustered at 0.0 for every text. It was replaced with hedge-word density, which cleanly separated the corpus: AI texts scored 2.4–16.3 hits per 100 words, all three human reference texts scored exactly 0.0.

**Weighted voting scheme:**

```
Long text  (≥ 40 words): combined = 0.50 × llm + 0.30 × stylometric + 0.20 × repetition
Short text (< 40 words): combined = (1/3) × llm + (1/3) × stylometric + (1/3) × repetition
```

LLM keeps the largest weight as the most semantically informed signal. Repetition gets the smallest weight as the newest, least-validated signal — a tie-breaker rather than a primary driver. This is implemented in `compute_confidence_ensemble()` in `scoring.py`, alongside the original 2-signal `compute_confidence()` which is retained for backward compatibility.

**Result:** the spec's "clearly AI" example, which scored 0.77 under the 2-signal system (just under the 0.80 threshold, landing in `uncertain`), scores 0.89 under the 3-signal ensemble — correctly crossing into `high_confidence_ai`. The repetition signal caught hedge-word density that the other two signals didn't directly measure.

**Blind spot:** Hedge/repetition heuristics are sensitive to genre. Poetry and persuasive rhetoric use repetition and emphatic qualifiers intentionally (refrains, anaphora, rhetorical "furthermore"s) and would score AI-like on this signal alone. This is mitigated by the signal's lower weight (0.20) in the ensemble.

---

### Stretch — Provenance certificate ("verified human")

A lightweight, optional verification step a creator can complete once. **This is explicitly not robust identity verification** — it is a non-triviality filter, documented honestly as such.

**How it works:**

1. `GET /verify-human/challenge` returns a randomly chosen open-ended prompt (e.g. "Describe, in your own words, why you started writing.")
2. The creator submits a freeform response via `POST /verify-human` with `{creator_id, response_text}`
3. The server rejects responses under 8 words or matching a small set of trivial strings ("n/a", "test", "idk", etc.) with HTTP 422
4. A response that passes is recorded in the `verified_creators` table with a timestamp

Once verified, every subsequent `POST /submit` response for that `creator_id` includes:

```json
"provenance_certificate": {
    "verified_human": true,
    "verified_at": "2025-06-01T10:00:00+00:00"
}
```

**Design decision — verification does not bypass detection.** A verified creator's content still runs through the full detection pipeline. The certificate is additional context shown alongside the verdict, not a free pass — this prevents verification from becoming a loophole that lets a creator post AI-generated content and skip detection entirely.

**Blind spot:** This filters out only trivially automated submissions. A determined bad actor with access to an LLM could write a passable freeform response and earn the badge. It is a UX nudge toward honest participation, not a security control — this is stated plainly rather than oversold.

---

### Stretch — Analytics dashboard

`GET /analytics` aggregates the existing audit log with no new storage layer — pure SQL aggregation against `audit_log`.

```bash
curl http://localhost:5000/analytics | python -m json.tool
```

Returns:

```json
{
  "total_decisions": 5,
  "verdict_distribution": {
    "uncertain": { "count": 3, "pct": 60.0 },
    "high_confidence_ai": { "count": 2, "pct": 40.0 }
  },
  "total_appeals": 1,
  "appeal_rate": 0.2,
  "appeal_rate_by_verdict": {
    "uncertain": 0.0,
    "high_confidence_ai": 0.5
  },
  "avg_confidence_by_verdict": {
    "uncertain": 0.6234,
    "high_confidence_ai": 0.8745
  }
}
```

**Three metrics, as required:**

1. **Verdict distribution** — count and percentage of each of the three verdict types across all decisions
2. **Appeal rate** — both overall (`appeals / total_decisions`) and broken down per verdict, so it's visible whether appeals concentrate on `high_confidence_ai` (expected, since that's the verdict creators are most likely to contest) versus spreading evenly
3. **Additional metric chosen — average confidence by verdict bucket** — reveals whether `uncertain` verdicts cluster near the threshold boundaries (0.21, 0.79) or spread evenly across the band. This is directly useful for evaluating whether the 0.80/0.20 thresholds are well-placed: if `uncertain` averages near 0.50, the band is doing its job; if it skews heavily toward one edge, the thresholds may need adjustment.

---

### Stretch — Multi-modal support (structured metadata)

`POST /submit` now accepts an optional `content_type` field: `"text"` (default) or `"metadata"`.

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "content_type": "metadata",
    "creator_id": "photographer-1",
    "metadata": {
      "software_used": "Midjourney v6"
    }
  }' | python -m json.tool
```

**New signal — `signals/metadata.py` (rule-based, pure Python):** checks `software_used`/`creation_tool` fields against a list of known AI-generation tool signatures (Midjourney, DALL-E, Stable Diffusion, Adobe Firefly, Runway, etc.) and checks for the presence of camera fields (`camera_model`, `iso`, `aperture`) that a genuine photograph typically retains.

| Scenario | Score | Verdict |
|---|---:|---|
| `software_used: "Midjourney v6"` | 0.95 | `high_confidence_ai` |
| `camera_model, iso, aperture` all present | 0.15 | `uncertain` |
| Camera fields + recognized photo-editing software | 0.05 | `high_confidence_human` |
| No metadata fields at all | 0.50 | `uncertain` |

**Confidence scoring for the metadata path:** the LLM and stylometric signals only apply to free text, so for `content_type: "metadata"` the metadata signal's score is used directly as the combined confidence — there's only one applicable signal, so ensemble weighting doesn't apply on this path. This is a deliberate scope limitation, documented here rather than hidden: a real multi-modal system would also analyze the image content itself, not just its metadata.

**Blind spot:** Purely metadata-based detection is trivially defeated by stripping or spoofing fields before upload (most platforms strip EXIF data on upload by default). Metadata signals here are circumstantial evidence, not proof, and the README and code comments say so directly rather than overstating reliability.

---



### `POST /submit`

Classify a piece of text. Rate limited: 10/hr, 60/hr, 200/day per IP.

**Request:**
```json
{ "text": "...", "creator_id": "..." }
```

**Response 201:**
```json
{
  "content_id": "<uuid>",
  "attribution": "high_confidence_ai | uncertain | high_confidence_human",
  "confidence": 0.8923,
  "label_text": "<display-ready string>",
  "signals": {
    "llm":         { "score": 0.95, "rationale": "..." },
    "stylometric": { "score": 0.727, "components": { ... } },
    "repetition":  { "score": 1.0,   "components": { "hedge_density": 8.7 } }
  },
  "short_text_warning": false,
  "signal_error": false,
  "content_type": "text",
  "provenance_certificate": { "verified_human": false, "verified_at": null },
  "submitted_at": "2025-06-01T14:31:00+00:00"
}
```

Submitting with `"content_type": "metadata"` instead of `"text"` routes through the metadata signal (see § Stretch features — Multi-modal support) and returns `"signals": {"metadata": {...}}` in place of the text-based signals.

**Errors:** 400 bad input · 429 rate limit exceeded

---

### `POST /appeal`

Contest a classification.

**Request:**
```json
{
  "content_id": "<uuid from POST /submit>",
  "creator_id": "<must match original submission>",
  "creator_reasoning": "<free text, max 1000 chars>"
}
```

**Response 200:**
```json
{
  "appeal_id": "<uuid>",
  "content_id": "<uuid>",
  "status": "under_review",
  "message": "Your appeal has been received and logged...",
  "logged_at": "..."
}
```

**Errors:** 400 bad input · 403 creator mismatch · 404 not found · 409 duplicate appeal

---

### `GET /log`

Returns audit log entries, newest first.

**Query params:** `type` (decision | appeal) · `creator_id` · `limit` (default 50, max 200)

---

### `GET /status/<content_id>`

Returns the current content record (verdict, confidence, status, timestamps).

---

### `GET /verify-human/challenge`  *(stretch)*

Returns a randomly chosen verification prompt.

```json
{ "challenge": "Describe, in your own words, why you started writing." }
```

### `POST /verify-human`  *(stretch)*

Submit a response to earn verified-human status for a `creator_id`.

**Request:** `{ "creator_id": "...", "response_text": "..." }`
**Response 200:** `{ "creator_id": "...", "verified_human": true, "verified_at": "..." }`
**Errors:** 400 missing fields · 422 response too short or templated

### `GET /analytics`  *(stretch)*

Returns aggregated detection patterns, appeal rates, and confidence statistics. See § Stretch features for full response shape.
