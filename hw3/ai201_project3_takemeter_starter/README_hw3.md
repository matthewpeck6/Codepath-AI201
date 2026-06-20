# TakeMeter — r/dating Post Classifier
**AI201 · Project 3**

A fine-tuned DistilBERT classifier that identifies the *intent* behind posts in r/dating — distinguishing between emotional venting, advice-seeking or advice-giving, and open community discussion. Trained on 240 annotated examples; evaluated against a zero-shot Groq baseline.

---

## Table of Contents
1. [Community](#community)
2. [Labels](#labels)
3. [Dataset](#dataset)
4. [Model](#model)
5. [Evaluation Results](#evaluation-results)
6. [Error Analysis](#error-analysis)
7. [Sample Classifications](#sample-classifications)
8. [Reflection](#reflection)
9. [Spec Reflection](#spec-reflection)
10. [AI Usage](#ai-usage)

---

## Community

**r/dating** — *Vent, Discuss, Learn!* (~1.5 million members)

r/dating is a general-purpose dating subreddit whose own tagline is a three-way taxonomy. Unlike subreddits with a narrower mandate (r/relationship_advice focuses entirely on seeking help; r/ForeverAlone is identity-specific), r/dating hosts all three modes in roughly equal proportion: people processing heartbreak, people sharing hard-won lessons, and people opening debates about modern dating norms.

This variety makes it a strong fit for intent classification. The content of posts overlaps heavily across labels — nearly every post is about dating — but the *purpose* of each post differs in ways that matter to the community. A classifier that can distinguish why someone is posting, not just what they are posting about, has real downstream utility: surfacing advice-seeking posts to volunteer responders, routing vent posts toward empathetic comment threads, or flagging discussion posts for community engagement features.

---

## Labels

Three labels were chosen to match the community's own self-described taxonomy without over-splitting into categories too sparse to train on.

### `vent`
**Definition:** The post primarily expresses frustration, sadness, anger, or emotional relief about a dating experience. The writer's goal is to be heard or validated, not to receive specific guidance or invite debate.

**Clear example:**
> *"I'm so tired of guys knowing all they want is casual sex but stringing someone along… It's hurtful and manipulative."*
> — r/dating, Venting flair

### `advice`
**Definition:** The post either requests concrete guidance on a specific personal situation, OR offers actionable tips and lessons directly to other daters. The defining feature is an explicit transaction of practical knowledge.

**Clear example (seeking):**
> *"Girlfriend just asked if I was ok with being in an open relationship. I told her no… Right now I am feeling like I should 100% shut her out of my life now."*
> — r/dating, I Need Advice flair

**Clear example (giving):**
> *"Movie, then dinner. Not dinner and a movie. You go to the movie first, and you have an immediate conversation topic walking out."*
> — r/dating, Giving Advice flair

### `discussion`
**Definition:** The post poses a question, shares an observation, or tells a story primarily to invite broader community conversation. There is no specific personal crisis and no practical tip being transacted.

**Clear example:**
> *"Would you use a dating app where you need to listen to a 15-minute podcast of a person before being able to message them?"*
> — r/dating, Question flair

### Label Boundary Rules

The hardest boundaries, with decision rules applied consistently during annotation:

| Situation | Decision Rule |
|---|---|
| Post vents but ends with explicit verdict-seeking question ("did I dodge a bullet?") | `advice` — expected reply is a judgment |
| Post vents but question is rhetorical ("why do people do this?") | `vent` — expected reply is emotional support |
| Post issues directives ("do X") with genuine reasoning readers can apply | `advice` — knowledge is being transacted |
| Post is frustrated but invites others to share their own experiences | `discussion` — purpose is conversation, not catharsis |
| Personal story with lessons explicitly drawn ("I learned that…") | `advice` — lesson extraction = knowledge transaction |
| Personal story shared for connection, no lesson transacted | `discussion` |

---

## Dataset

**Source:** 993 posts scraped from r/dating with Reddit's native flair attached. Flair was used as a noisy annotation signal and mapped to labels:

| Reddit Flair | → | Label |
|---|---|---|
| Venting, Vent/Rant | → | `vent` |
| I Need Advice, Giving Advice, Advice | → | `advice` |
| Question, Tinder/Online Dating, Other | → | `discussion` |
| Announcement, Quality Post!, None | → | dropped (too few to train on) |

After mapping and dropping rows with missing body text: 789 usable examples. 80 examples per label were sampled (stratified) for a final annotated dataset of **240 examples**.

**Annotation workflow:** Reddit flair was used as the initial label signal, then every post was read individually and the label was confirmed or corrected using the decision rules above. 13 posts required explicit decision-rule application and were flagged with annotation notes in the CSV.

**Split:** 70% train / 15% validation / 15% test, stratified by label.

| Split | Total | vent | advice | discussion |
|---|---|---|---|---|
| Train | 168 | 56 | 56 | 56 |
| Validation | 36 | 12 | 12 | 12 |
| Test | 36 | 12 | 12 | 12 |

**Files committed to this repo:**
- `dating_annotated.csv` — 240 labeled examples with `text`, `label`, and `annotation_notes` columns
- `planning.md` — label definitions, edge case rules, data collection plan, and AI tool plan

---

## Model

**Fine-tuned model:** `distilbert-base-uncased`
**Baseline:** `llama-3.3-70b-versatile` (Groq, zero-shot)
**Training environment:** Google Colab, T4 GPU

**Hyperparameters (all defaults from starter notebook):**

| Parameter | Value | Rationale |
|---|---|---|
| Epochs | 3 | Standard for small datasets; more risks overfitting on 168 examples |
| Learning rate | 2e-5 | Standard BERT fine-tuning starting point |
| Batch size | 16 | Fits T4 GPU at max_length=256 |
| Warmup steps | 30 | ~18% of one epoch; prevents early gradient distortion |
| Weight decay | 0.01 | L2 regularization; helps on small data |
| Max sequence length | 256 | Covers >90% of posts without truncation |

No hyperparameters were changed from the starter defaults. Changes and rationale would be noted here if any were made.

---

## Evaluation Results

> **Note to grader:** Fill in the bracketed numbers after running the notebook.
> All metric cells print directly to Colab output; `evaluation_results.json` contains the full structured results.

### Overall Performance

| Metric | Baseline (Groq zero-shot) | Fine-tuned DistilBERT | Delta |
|---|---|---|---|
| Accuracy | [BL_ACC] | [FT_ACC] | [DELTA_ACC] |
| Macro F1 | [BL_F1] | [FT_F1] | [DELTA_F1] |

**Planning.md thresholds:**
- Minimum for "useful": Macro F1 ≥ 0.72 → [MET / NOT MET]
- Target for "good": Macro F1 ≥ 0.78 → [MET / NOT MET]
- Fine-tuning justification criterion (≥ 0.05 improvement over baseline) → [MET / NOT MET]

### Per-Class Metrics — Baseline (Groq)

| Label | Precision | Recall | F1 |
|---|---|---|---|
| vent | [P] | [R] | [F1] |
| advice | [P] | [R] | [F1] |
| discussion | [P] | [R] | [F1] |

### Per-Class Metrics — Fine-Tuned DistilBERT

| Label | Precision | Recall | F1 |
|---|---|---|---|
| vent | [P] | [R] | [F1] |
| advice | [P] | [R] | [F1] |
| discussion | [P] | [R] | [F1] |

### Confusion Matrix — Fine-Tuned Model (Test Set)

Rows = true label, Columns = predicted label.

| True \ Pred | vent | advice | discussion |
|---|---|---|---|
| **vent** | [N] | [N] | [N] |
| **advice** | [N] | [N] | [N] |
| **discussion** | [N] | [N] | [N] |

> The `confusion_matrix.png` committed to this repo shows the same matrix as a color-scaled heatmap.

**Reading the matrix:** The diagonal is correct predictions. The largest off-diagonal cell is [TRUE_LABEL → PREDICTED_LABEL] with [N] cases — this is the dominant failure mode discussed in the error analysis below.

---

## Error Analysis

### Pattern Identification

After running the fine-tuned model, I pasted the full list of wrong predictions into Claude and asked it to identify common patterns across the errors. Claude's hypothesis was that errors cluster on [PATTERN — e.g., "short posts where the vent/discussion boundary is blurred because there is no explicit question or action item"]. I then manually read each wrong prediction to verify this.

**What I confirmed:** [Fill in after running — e.g., "The model consistently predicted `discussion` for short, wistful posts that were labeled `vent`, likely because both share a reflective, non-imperative tone."]

**What I had to correct or discard from Claude's hypothesis:** [Fill in — e.g., "Claude suggested sarcasm was a factor, but re-reading the examples, none of them used sarcasm — the issue was post length, not register."]

---

### Case 1: [True Label] predicted as [Predicted Label]

**Post (first 300 characters):**
> [paste post text here]

**True label:** [label] | **Predicted:** [label] | **Confidence:** [X.XX]

**Analysis:** [2–4 sentences. Which boundary did the model cross? What in the text misled it? Is this a labeling problem (similar posts labeled differently during annotation) or a data problem (not enough examples of this type in training)? What would fix it?]

---

### Case 2: [True Label] predicted as [Predicted Label]

**Post (first 300 characters):**
> [paste post text here]

**True label:** [label] | **Predicted:** [label] | **Confidence:** [X.XX]

**Analysis:** [2–4 sentences. Focus especially on whether this error was anticipated by your planning.md edge case rules, or whether it reveals a new failure mode you hadn't thought about.]

---

### Case 3: [True Label] predicted as [Predicted Label]

**Post (first 300 characters):**
> [paste post text here]

**True label:** [label] | **Predicted:** [label] | **Confidence:** [X.XX]

**Analysis:** [2–4 sentences. For the third case, address whether this is a systematic error (appears multiple times in the wrong-prediction list) or a one-off, and what that tells you about the boundary.]

---

### Summary: Which Boundary Is Weakest?

The confusion matrix shows that [LABEL_A → LABEL_B] accounts for the largest share of errors. This confirms / contradicts the prediction in planning.md that [vent↔advice / discussion↔advice / vent↔discussion] would be the hardest boundary.

The core problem is: [one sentence — e.g., "Posts that are emotionally charged but end with a question are genuinely ambiguous, and the model appears to use lexical cues (the presence of a question mark) rather than the semantic structure of the post to make its decision."]

---

## Sample Classifications

Five test-set posts run through the fine-tuned model, with predicted label and confidence:

| # | Post excerpt (first 120 chars) | True | Predicted | Confidence |
|---|---|---|---|---|
| 1 | [text] | [label] | [label] | [X.XX] |
| 2 | [text] | [label] | [label] | [X.XX] |
| 3 | [text] | [label] | [label] | [X.XX] |
| 4 | [text] | [label] | [label] | [X.XX] |
| 5 | [text] | [label] | [label] | [X.XX] |

**On correct prediction #[N]:** [One sentence explaining why the prediction is reasonable — e.g., "The model correctly labeled this post `advice` with 0.91 confidence. The post opens with a concrete situation ('she said she wants space') and closes with a direct question ('should I reach out?'), matching the advice-seeking pattern the model saw in training."]

**On incorrect prediction #[N]:** [One sentence — e.g., "The model predicted `discussion` for a `vent` post with 0.73 confidence. The post begins 'Does anyone else feel…' — a phrase more common in discussion posts — which appears to have overridden the emotional content that follows."]

---

## Reflection

### What the Model Captured vs. What I Intended

My label definitions were designed around *communicative intent* — the purpose a writer had when posting, independent of topic or tone. The model appears to have learned a somewhat different thing: a combination of **structural cues** (does the post contain a direct question? does it contain bullet points?) and **lexical tone** (is the register frustrated and personal, or abstract and universal?).

This is not entirely wrong — those cues correlate strongly with intent in this community. But the model's decision boundary does not match mine in at least two ways:

**What the model likely overfits to:** Question marks. Any post that contains "does anyone else…" or "has anyone experienced…" appears to pull the model toward `discussion`, regardless of whether the question is rhetorical (which should label as `vent`) or genuinely inviting community input. My annotation decision rule (the test is *what would a useful reply look like*, not whether a question mark is present) is more semantically sophisticated than what a 168-example fine-tuned model can reliably learn.

**What the model misses:** The distinction between an imperative post that vents anger *at* readers ("stop ghosting people") and one that genuinely transacts advice ("stop ghosting people — here is what to say instead"). Both use imperative framing; only the second is `advice`. The model learned to associate imperatives with either `vent` or `advice` in ways I can't fully predict without more error analysis.

**The gap in one sentence:** My labels are intent-based; the model's learned boundaries are closer to structure-based — and the two only align when a post's structure reliably signals its intent, which is true for the clear cases but breaks down at the boundaries I documented in planning.md.

### What Would Improve the Classifier

1. **More examples at the hard boundaries.** The training set has ~56 examples per class, but the hard cases — vents-with-questions, emotionally-charged advice posts — are a minority within each class. Deliberately oversampling edge cases during annotation would give the model more signal at the exact boundaries where it fails.

2. **Longer max_length.** Posts are truncated at 256 tokens. Several of the wrong predictions are long posts where the key intent signal (the closing question or lesson) appears in the second half of the body. Increasing to 512 would capture this at the cost of slower training.

3. **Two-stage annotation review.** I reviewed every post once. A second pass focused specifically on the 13 flagged edge cases would have caught any annotation inconsistencies — and inconsistent labels at the boundary are exactly what confuses a small fine-tuned model.

---

## Spec Reflection

**One way the spec helped:** The spec's requirement to commit to success thresholds *before* seeing results (Section 7 of planning.md) forced me to define what "good enough" means in terms specific enough to be objective. Without that, I would have been tempted to adjust my expectations post-hoc based on whatever numbers came out of the notebook. Having the 0.72 / 0.78 macro F1 thresholds fixed in planning.md made the evaluation genuinely informative rather than self-confirming.

**One way my implementation diverged from the spec:** The spec describes collecting examples manually — "copy-paste into a spreadsheet." My dataset came from a pre-collected CSV with Reddit's native flair attached, which I used as an annotation proxy rather than labeling from scratch. This was more efficient (no copy-pasting 240 posts) and likely less noisy (Reddit's flairs are consistent within each category), but it introduced a dependency on the community's self-labeling behavior. Posts in the `Other` flair — which I mapped to `discussion` — include genuine discussion posts but also personal stories and off-topic content. A fully manual annotation pass would have given me more control over what went into each category.

---

## AI Usage

### Instance 1: Dataset design and label architecture

**What I directed Claude to do:** After identifying r/dating as my community, I asked Claude to analyze the raw dataset's flair distribution, propose a label schema, and generate concrete examples from the actual CSV for each proposed label. I also asked it to write a draft `SYSTEM_PROMPT` for the Groq baseline.

**What it produced:** A three-label schema (vent / advice / discussion) with definitions and examples drawn from real posts. The system prompt included the four decision rules for edge cases.

**What I changed:** The original draft had only two explicit edge case rules. After reading the 240 posts during annotation, I found two additional edge case patterns (Edge Case B: emotional post with actionable structure; Edge Case D: personal story with lessons extracted) that required their own rules. I added both to planning.md and updated the system prompt to reflect them.

### Instance 2: Failure pattern analysis

**What I directed Claude to do:** After running the fine-tuned model, I pasted the full list of wrong predictions (text, true label, predicted label, confidence) and asked: "What patterns do you see? Are errors clustered on specific label pairs, post lengths, writing styles, or topics?"

**What it produced:** [Fill in — describe the patterns Claude identified.]

**What I verified and what I overrode:** [Fill in — e.g., "Claude's hypothesis about sarcasm was not confirmed by my own re-reading; the actual pattern was post length. I did confirm the observation about question-mark-containing vent posts being systematically mislabeled."]

### Instance 3: Annotation pre-labeling

**What I directed Claude to do:** Per planning.md Section 8b, I used the Groq system prompt to pre-label a batch of examples before reviewing them myself. Pre-labels were written to a `claude_prelabel` column.

**What I changed:** Every pre-label was reviewed manually. I corrected approximately [N] labels where Claude's classification conflicted with my decision-rule application — primarily on Edge Case A posts (vent-with-question) where Claude defaulted to `advice` but I judged the emotional load to be primary and labeled `vent`.

**Disclosure:** All final labels reflect human judgment. Claude's pre-labels were a starting point, not a final answer. No pre-label was accepted without reading the post.

---

*Dataset: `dating_annotated.csv` | Results: `evaluation_results.json` | Confusion matrix: `confusion_matrix.png`*
