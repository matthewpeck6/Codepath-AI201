# planning.md
## TakeMeter — Project 3 | r/dating Classifier
**AI201 | Author: [Your Name]**

---

## 1. Community

**Chosen community:** r/dating — *Vent, Discuss, Learn!*

r/dating is a general-purpose dating subreddit with ~1.5 million members. Its tagline ("Vent, Discuss, Learn") is itself a taxonomy: the community self-sorts into emotional release, open conversation, and knowledge exchange. Unlike advice-specific subreddits (r/relationship_advice) or identity-specific ones (r/ForeverAlone), r/dating attracts a wide cross-section of posters — people processing heartbreak, people sharing tips from hard-won experience, and people opening debates about modern dating norms. That variety makes it a strong fit for classification: posts genuinely differ in purpose, tone, and what the poster wants from readers. A classifier that can distinguish *why* someone is posting — not just what they're posting about — has real downstream utility for community moderation, content routing, and support tooling.

---

## 2. Labels

Three labels cover the meaningful variation in this community without over-splitting into categories too thin to train on.

---

### `vent`
**Definition:** The post is primarily expressing frustration, sadness, anger, or emotional relief about a dating experience — the writer's goal is to be heard or validated, not to receive specific guidance or invite debate.

**Example 1 (clear):**
> *Title: RANT: Dating as a woman is NOT easier. Finding love as a woman is NOT easier.*
> "I'm part of the foreveralone subreddit because I haven't had a serious relationship in 5 years. Yet none of the posts there describe me… I'm a woman, objectively physically attractive, it's very easy for me to get 'dates.' As a result, I get dismissed every single time I talk about loneliness."

This is unambiguously `vent`: the writer is not requesting help, is not posing a question to the community, and is not offering a lesson. The post ends on frustration, not a call to action.

**Example 2 (clear):**
> *Title: Stop stringing people along just for sex.*
> "I'm so tired of guys knowing all they want is casual sex but stringing someone along… It's hurtful and manipulative. Please guys that are doing this stop."

Pure emotional release directed outward. The imperative at the end ("please stop") is moral appeal, not a request for advice from readers.

**Uncertain case — see Section 3.**

---

### `advice`
**Definition:** The post either requests concrete guidance on a specific personal situation, OR offers actionable tips and lessons directly to other daters — the defining feature is an explicit transaction of practical knowledge.

**Example 1 (clear — advice-seeking):**
> *Title: Girlfriend just asked if I was ok with being in an open relationship.*
> "I told her no… Right now I am feeling like I should 100% shut her out of my life now."

The writer has a specific situation and implicitly wants to know: am I right to leave? Is this salvageable? The post is anchored in a concrete dilemma with a decision to make.

**Example 2 (clear — advice-giving):**
> *Title: Movie, then dinner. Not dinner and a movie.*
> "You go to the movie first, and you have an immediate conversation topic walking out — you've just shared an experience… Go to the movie first."

A specific, actionable tip with reasoning. The writer is not venting and not opening a debate; they're transferring a concrete practice.

**Uncertain case — see Section 3.**

---

### `discussion`
**Definition:** The post poses a question, shares an observation, or tells a story primarily to invite broader community conversation — there is no specific personal crisis and no practical tip being transacted.

**Example 1 (clear — open question):**
> *Title: What are your "yellow flags" when it comes to dating?*
> "Yellow flags as in no imminent danger or anything overtly alarming, but still indicators of something not great."

Explicitly invites the community to share their own answers. The writer is not processing an emotion and is not giving or seeking situational guidance.

**Example 2 (clear — observation/story):**
> *Title: Do you ever wonder what the person you're going to end up with is doing?*
> "Whenever I feel sad, alone, or frustrated, I think about him. I wonder where he is and what he's doing… I think about how much I wish he were here with me."

A reflective, universalizing observation meant to spark community resonance. Tone is wistful rather than agitated, and the post asks whether others share the feeling — not for help with a specific problem.

**Uncertain case — see Section 3.**

---

## 3. Hard Edge Cases

*Updated after annotation pass: all examples below are real posts from the dataset.*

### Edge Case A: The Vent That Ends With a Question (vent ↔ advice)

The most common boundary problem. Many posts open with emotional processing and close with a question — but the question can be rhetorical (seeking comfort) or real (seeking a verdict).

**Decision rule:** The test is *what would a useful reply look like?* If the expected reply is emotional support, it's `vent`. If the expected reply is a concrete judgment or recommendation, it's `advice`.

**Three real cases from annotation:**

*"Did this guy sexually assault me or?"* — Title is a question, but body is trauma processing. The writer narrates what happened and the question functions as a cry for validation, not a legal query. **Labeled `vent`.** A helpful reply would be supportive, not analytical.

*"First dates feel like job interviews to me now."* — Ends with "has anyone else experienced this?" but 95% is venting about 28 exhausting first dates. The question seeks commiseration. **Labeled `vent`.** Emotional load outweighs the question.

*"Girls ends it with me after I bring up concerns over her never offering to pay"* — Ends with "Did I dodge a bullet here?" This is a real verdict-seeking question about a concrete decision. **Labeled `advice`.** The expected reply is a judgment ("yes/no, and why").

---

### Edge Case B: The Emotional Post With Actionable Structure (vent ↔ advice)

Some posts are emotionally charged but structured as advice — bullet points, imperatives, lessons extracted. The question is whether the *function* is cathartic release or knowledge transaction.

**Decision rule:** If the post issues directives with genuine reasoning that readers can apply, it's `advice` even if the tone is frustrated. If the imperative framing is venting anger *at* readers with no usable content, it's `vent`.

**Two real cases from annotation:**

*"Sick of being a means to an end"* — Title reads as frustration (vent), but body is a structured action list: "start putting yourself first, learn to say NO, make decisions based on behavioral patterns not feelings." **Labeled `advice`** — the content is genuinely usable by readers regardless of the emotional framing.

*"A reminder for myself and anyone else who needs it:"* — Inspirational tone, but body is a behavioral checklist ("if they really want to be with you, they will: reply in a timely manner, text you first…"). Directed at readers, actionable. **Labeled `advice`.**

---

### Edge Case C: The Frustrated Observation (discussion ↔ vent)

Posts that begin with frustrated tone but function as conversation-openers rather than emotional catharsis.

**Decision rule:** If the post explicitly invites others to share experiences or debate, or if the analytical structure outweighs the emotional register, label it `discussion`. Frustration alone doesn't make something `vent` — the question is whether the *purpose* is release vs. conversation.

**Three real cases from annotation:**

*"I'm so tired of the 'the more you ignore them, the more interested they become' thing"* — Frustrated title, but body shares a personal observation about this cliché and implicitly invites others to weigh in. **Labeled `discussion`** — the frustration is incidental to the observation being offered.

*"Any other perpetual single ladies here who feel broken?"* — Emotionally charged, but explicitly asks if others share the feeling — the writer wants community solidarity, not catharsis. **Labeled `discussion`.**

*"This sub is nonstop complaining with little advice on actual dating."* — Could invite debate (discussion) but the writer is directing frustration *at* the community with no genuine invitation to respond. **Labeled `vent`** — the absence of an invitation to respond is the deciding signal.

---

### Edge Case D: The Personal Story With Lessons Extracted (discussion ↔ advice)

Some posts narrate a dating experience in detail. The key question is whether the story serves as a lesson or as a shared experience.

**Decision rule:** If the post closes with explicit lessons drawn from the story ("I learned that…", "what I take from this is…"), label it `advice`. If the story is shared for connection with no lesson transacted, label it `discussion`.

**Real case from annotation:**

*"My dating story."* (Giving Advice flair) — Reads like a narrative dump across multiple failed relationships, but closes with explicit lessons drawn from each. **Labeled `advice`** — the lesson-extraction makes it a knowledge transaction, not just a story.

---

## 4. Mutual Exclusivity Check

The three-label system passes the one-post-one-label test in the large majority of cases:

- A post can be **both emotionally charged and advice-seeking** — resolved by Edge Case A rule (explicit question → `advice`)
- A post can be **both a tip and a conversation opener** — resolved by Edge Case B rule (imperative framing → `advice`)
- A post can be **both a story and emotionally colored** — resolved by Edge Case C rule (resolved/past-tense → `discussion`, present distress → `vent`)

The labels do not overlap structurally: `vent` is about emotional state, `advice` is about knowledge transaction, and `discussion` is about community conversation. The edge cases arise when posts mix two of these functions, and the decision rules above always pick one primary function.

Estimated ambiguity rate: ~10–15% of posts will require applying a decision rule. That is acceptable.

---

## 5. Data Collection Plan

**Source:** The dataset (`dating_data.csv`) contains 993 posts from r/dating with Reddit's native flair. After mapping flairs to labels and dropping rows with unmapped flair or missing body text, the usable pool is 789 examples. From that pool, 80 examples per label were sampled for a **final annotated dataset of 240 examples**.

| Label | Sampled | % of total |
|---|---|---|
| `vent` | 80 | 33.3% |
| `advice` | 80 | 33.3% |
| `discussion` | 80 | 33.3% |

**Balance:** Perfectly balanced by design (stratified sampling). No class exceeds 70% of the dataset; no resampling needed.

**Annotation workflow:** All 240 examples were manually reviewed post-sampling. Reddit flair was used as the initial label signal, then each post was read individually and the label was confirmed or corrected using the decision rules in Section 3. 13 posts were flagged with annotation notes documenting the edge case and decision rationale; these are preserved in the `annotation_notes` column of the CSV.

**If a label becomes underrepresented:** The pool of 789 examples provides headroom — additional examples can be drawn from the remaining 549 unlabeled posts in the same pool without any new data collection. The 70/15/15 split gives ~56 training examples per class at 240 total; acceptable for DistilBERT fine-tuning, though more data would improve performance.

---

## 6. Evaluation Metrics

**Primary metric: macro-averaged F1**

Accuracy alone is insufficient here because the classes, while roughly balanced, are not perfectly equal — and more importantly, all three label types have equal community value. Macro F1 weights each class equally regardless of size, so a model that excels at `vent` and `discussion` but fails on `advice` (the smallest class) will be penalized appropriately. A model that merely learns to predict the majority class would score ~36% accuracy but 0% on minority classes — macro F1 would expose this immediately while accuracy would obscure it.

**Secondary metrics:**

- **Per-class precision and recall** — For a community moderation tool, false negatives on `advice` posts (labeling someone's genuine request for help as venting) are a different failure mode than false positives. The confusion matrix will reveal which label boundaries are leaking.
- **Confusion matrix** — The three-class confusion matrix will show whether errors cluster on the predicted hard boundaries (vent↔advice, discussion↔advice) as anticipated, or whether there are unexpected failure patterns.

**Baseline comparison:** The Groq zero-shot baseline (llama-3.3-70b-versatile) will be run on the identical test set. Fine-tuning should be judged relative to this baseline — a fine-tuned model that underperforms a zero-shot LLM is not a useful artifact.

---

## 7. Definition of Success

**Minimum threshold for "useful":** Macro F1 ≥ 0.72 on the held-out test set. At this threshold, the classifier is right about three-quarters of the time across all classes and could plausibly be used to auto-tag incoming posts for community routing (e.g., surfacing `advice` posts to a volunteer responder queue) with human spot-checking.

**Target threshold for "good":** Macro F1 ≥ 0.78. At this level, per-class recall is likely high enough that the classifier catches most genuine advice-seeking posts — the highest-stakes label for a support-oriented use case.

**Explicit failure condition:** If fine-tuned DistilBERT does not outperform the Groq zero-shot baseline by at least 0.05 macro F1, the fine-tuning is not justified. The value of a small fine-tuned model over a large zero-shot model is speed and cost, not just accuracy — so it must also be meaningfully more accurate to earn its place.

**Success criteria are objective:** At the end of the project, I will compute macro F1 on the locked test set. The threshold (0.72 minimum, 0.78 target) is fixed now and will not be adjusted after seeing results.

---

## 8. AI Tool Plan

### 8a. Label Stress-Testing

**Plan:** Before annotating, I will give Claude (or another LLM) the three label definitions and edge case rules and ask it to generate 10 posts that sit at the boundary between two labels — specifically targeting the vent↔advice boundary (Edge Case A), since that's the most common failure mode anticipated.

**Acceptance criterion:** If the AI generates posts I cannot classify in under 10 seconds using the decision rules in Section 3, the definitions need tightening. I will revise Section 3 before annotating a single example. If I can classify all 10 generated posts cleanly, the definitions are ready.

**Prompt I'll use:**
> "Here are my three label definitions and edge case rules: [paste Section 2 and 3]. Generate 10 posts from r/dating that sit at the boundary between `vent` and `advice`. Make them genuinely ambiguous — posts where a reasonable annotator could go either way."

### 8b. Annotation Assistance

**Plan:** I will use Claude to pre-label the full 789-example dataset using the `SYSTEM_PROMPT` defined in the notebook (Section 5). Pre-labels will be written to a `claude_prelabel` column in the CSV. I will then manually review and correct any example where the pre-label conflicts with my own first-pass label.

**Tracking:** Every example pre-labeled by Claude will be flagged with `prelabeled: true` in a separate column. The final label column will always reflect my human judgment — Claude's pre-label is a starting point, not a final answer.

**Disclosure:** The README and AI usage section will note that Claude was used for pre-labeling and that all pre-labels were human-reviewed before being used as training data.

### 8c. Failure Analysis

**Plan:** After Section 4 runs and the wrong-prediction list is printed, I will paste the full list of misclassified examples (text, true label, predicted label, confidence) into Claude and ask:

> "Here are the examples my classifier got wrong. What patterns do you see? Are the errors clustered on specific label pairs, post lengths, writing styles, or topics? What does this suggest about which label boundary is weakest?"

**What I'll look for:** Whether errors cluster on the anticipated vent↔advice boundary, or whether the model fails on an unexpected boundary (e.g., discussion↔vent). I will verify any pattern Claude identifies by manually reading 5–10 examples in that cluster myself before citing it in the README — AI-identified patterns are hypotheses, not conclusions.

---

## 9. Open Questions / Risks

- **Flair noise:** Reddit flair is user-applied, not editorially enforced. Some posts tagged "Other" may clearly belong to `vent` or `advice` — by dropping all `None`/`Other`/`Announcement` flairs, I may be discarding usable data. Mitigation: manual review of a random 20-example sample from dropped rows to confirm they're genuinely unclassifiable.
- **Text length variance:** Body lengths range from 55 to 19,294 characters. DistilBERT truncates at 512 tokens; very long posts will lose their endings. If error analysis shows long posts systematically misclassified, I'll experiment with truncating from the middle rather than the end.
- **Class drift:** The dataset spans 2020 (COVID era). Norms referenced in posts (lockdown dating, mask-wearing) may not generalize to current community language. This is a known limitation, not a fixable one at this stage.
