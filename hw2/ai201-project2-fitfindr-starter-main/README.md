# FitFindr

An AI-powered secondhand shopping assistant that finds thrifted pieces and suggests how to style them with your existing wardrobe.

---

## Setup

```bash
# Install dependencies
pip install gradio groq python-dotenv pytest

# Add your API key to .env
echo "GROQ_API_KEY=your_key_here" > .env
# or: echo "ANTHROPIC_API_KEY=your_key_here" > .env

# Run the app
python app.py
# → open http://localhost:7860

# Run tests
pytest tests/
```

**Without an API key:** `search_listings` works fully. The two LLM tools (`suggest_outfit`, `create_fit_card`) return a labelled mock string so you can test the planning loop structure without a key.

---

## Tool Inventory

### Tool 1: `search_listings`

**Purpose:** Searches the mock listings dataset for secondhand items matching the user's keywords, size, and price ceiling. No LLM call — pure Python filtering and scoring.

**Inputs:**
| Parameter | Type | Meaning |
|---|---|---|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size to filter by, or `None` to skip. Case-insensitive substring match — `"M"` matches `"S/M"` |
| `max_price` | `float \| None` | Maximum price inclusive in USD, or `None` to skip |

**Output:** `list[dict]` — matching listing dicts sorted by keyword relevance, best match first. Each dict contains:
- `id` (str), `title` (str), `description` (str)
- `category` (str): one of `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`
- `style_tags` (list[str]), `colors` (list[str])
- `size` (str), `condition` (str): `excellent` / `good` / `fair`
- `price` (float), `brand` (str | None), `platform` (str): `depop` / `thredUp` / `poshmark`

Returns `[]` on no match — never raises.

---

### Tool 2: `suggest_outfit`

**Purpose:** Given the top thrifted item and the user's wardrobe, asks an LLM to suggest 1–2 complete outfit combinations. Handles an empty wardrobe gracefully with a separate prompt branch.

**Inputs:**
| Parameter | Type | Meaning |
|---|---|---|
| `new_item` | `dict` | A listing dict (the top `search_listings` result) |
| `wardrobe` | `dict` | Dict with `"items"` key containing a list of wardrobe item dicts. May be empty |

Each wardrobe item has: `id`, `name`, `category`, `colors` (list), `style_tags` (list), optional `notes`.

**Output:** `str` — non-empty string with outfit suggestions. If the wardrobe is empty, the LLM provides general styling advice (what pieces complement this item, what vibe it creates) rather than referencing specific owned pieces.

---

### Tool 3: `create_fit_card`

**Purpose:** Takes the outfit suggestion and item details and generates a short, casual OOTD caption — the kind a real person would post on Instagram or TikTok. Uses a higher LLM temperature (0.9) so outputs vary across runs.

**Inputs:**
| Parameter | Type | Meaning |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit`. Must be non-empty |
| `new_item` | `dict` | The listing dict — used to pull `title`, `price`, and `platform` into the caption |

**Output:** `str` — a 2–4 sentence caption that mentions the item name, price, and platform once each, describes the outfit vibe in specific visual terms, and sounds casual and personal.

---

## How the Planning Loop Works

The loop runs sequentially and checks each step's output before proceeding. It exits early the moment any step produces no usable result.

```
User query
    │
    ▼
Step 1  Parse query (regex, no LLM)
        Extract: description, size, max_price
        Store in session["parsed"]
    │
    ▼
Step 2  search_listings(description, size, max_price)
        Store in session["search_results"]
        ┌── empty? ──► set session["error"], return session  ◄── EARLY EXIT
        │
        └── results found ──► session["selected_item"] = results[0]
    │
    ▼
Step 3  suggest_outfit(selected_item, wardrobe)
        Store in session["outfit_suggestion"]
        ┌── empty/LLM error? ──► set session["error"], return session  ◄── EARLY EXIT
        │
        └── outfit string ──► proceed
    │
    ▼
Step 4  create_fit_card(outfit_suggestion, selected_item)
        Store in session["fit_card"]
    │
    ▼
Return session  (error = None, all outputs populated)
```

**Key design decisions:**

- **Query parsing is regex-only.** Size tokens (XS, S, M, L, XL, S/M, W30 etc.) and price triggers (`under $30`) are extracted with patterns, not an LLM call. This keeps the step fast and free.

- **The loop never calls a downstream tool with empty input.** After `search_listings`, if `results == []`, the loop returns immediately without ever touching `suggest_outfit`. This means the failure mode for each tool is tested at the boundary, not discovered inside it.

- **Tools receive plain values, not the session dict.** Each tool is called with `search_listings(description, size, max_price)` — it doesn't know about the session. This keeps the tools independently testable and the loop the single point of orchestration.

- **The top result is always selected.** `selected_item = results[0]`. The list is sorted by keyword-overlap score, so `results[0]` is the best semantic match that also passes the hard price and size filters.

---

## State Management

All state for a single interaction lives in one session dict created by `_new_session()`. No global variables.

| Field | Written by | Read by | Purpose |
|---|---|---|---|
| `session["query"]` | `_new_session` | error messages | Original query; never mutated |
| `session["parsed"]` | planning loop step 2 | planning loop step 3 | Parsed description/size/price passed to `search_listings` |
| `session["search_results"]` | planning loop step 3 | planning loop step 4 | Full ranked result list; `results[0]` becomes `selected_item` |
| `session["selected_item"]` | planning loop step 4 | steps 5 & 6, `app.py` | The listing dict; same Python object passed to both downstream tools |
| `session["wardrobe"]` | `_new_session` | planning loop step 5 | Never mutated; passed directly to `suggest_outfit` |
| `session["outfit_suggestion"]` | planning loop step 5 | step 6, `app.py` | LLM string; passed as `outfit` arg to `create_fit_card` |
| `session["fit_card"]` | planning loop step 6 | `app.py` | Primary user-facing output |
| `session["error"]` | planning loop (any step) | `app.py` | `None` on success; human-readable string on any early exit |

**State continuity check (from `agent.py` `__main__`):**
```python
assert session["selected_item"] is session["search_results"][0]
# → passes: same dict object, not a copy
```

---

## Error Handling

### Tool 1: `search_listings` → no results

**Trigger:** Query that matches no listings after price and size filtering.

**Test command:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# → []
```

**Agent response:**
> "No listings found matching 'designer ballgown size XXS under $5'. Try broadening your search — remove the size or price filter, or use more general keywords."

`session["fit_card"]` and `session["outfit_suggestion"]` remain `None`. The planning loop exits before calling `suggest_outfit`.

---

### Tool 2: `suggest_outfit` → empty wardrobe

**Trigger:** User selects "Empty wardrobe (new user)" in the UI.

**Test command:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
item = search_listings('vintage graphic tee', max_price=50)[0]
print(suggest_outfit(item, get_empty_wardrobe()))
"
```

**Agent response:** Rather than crashing or returning an empty string, `suggest_outfit` detects `wardrobe["items"] == []` before building the prompt and switches to a general styling branch — the LLM is asked what types of pieces and colors complement the item, without being told to reference specific owned pieces. The planning loop continues normally.

This is **not treated as an error** — an empty wardrobe is a valid new-user state.

---

### Tool 3: `create_fit_card` → empty outfit string

**Trigger:** `outfit` argument is empty or whitespace-only (e.g. LLM returned nothing).

**Test command:**
```bash
python -c "
from tools import search_listings, create_fit_card
item = search_listings('vintage graphic tee', max_price=50)[0]
print(create_fit_card('', item))
"
# → Couldn't generate a fit card — outfit details were missing.
```

**Agent response:** The guard at the top of `create_fit_card` catches this *before* any LLM call. Returns a clear error string. No exception, no wasted API token.

---

## Spec Reflection

**What matched the plan exactly:**

- The three-step gate pattern (check result → proceed or exit early) implemented exactly as described in `planning.md`. The no-results path was easy to test precisely because the session dict made the state visible — `session["fit_card"] is None` confirmed the loop exited before reaching `create_fit_card`.

- The regex parser handled all example queries correctly: `"vintage graphic tee under $30"` → `{description: "vintage graphic tee", size: None, max_price: 30.0}`; `"90s track jacket size M under $40"` → `{description: "90s track jacket", size: "M", max_price: 40.0}`.

- The empty-wardrobe branch in `suggest_outfit` worked without any special handling in the planning loop — the tool itself absorbed the case.

**What I had to adjust:**

- **Scoring too broad.** The initial keyword scorer matched too liberally — a query for `"track jacket"` returned a silk slip dress (because its description mentioned "layering"). The fix was to score against `title + description + style_tags` rather than the full description blob, and to require a score > 0 (any overlap) rather than a minimum threshold. In hindsight, requiring score ≥ 2 for multi-word queries would improve precision further.

- **Size parsing edge case.** The regex `\b(M)\b` matched the "M" inside "medium" and "minimal" in descriptions, producing false size filters. Fixed by anchoring to known size tokens (XS/S/M/L/XL/XXL/XXS/S/M/M/L and W\d{2}) and applying the filter only against listing `size` fields, not description text.

- **`create_fit_card` error vs. session error.** The spec said to set `session["error"]` when `create_fit_card` returns an error string. In the implementation, the loop detects this by checking whether the returned string contains the known error prefix — which is fragile. A cleaner design would have `create_fit_card` return a `(str, bool)` tuple where the bool indicates success. Left as-is for now; flagged as a stretch improvement.

---

## AI Tool Usage

### Instance 1 — `search_listings` implementation

**Input given to Claude:** The Tool 1 spec block from `planning.md` (inputs with types, return value field list, failure mode), plus the first 3 listing dicts from `listings.json` as concrete data shape examples.

**What it produced:** A working `search_listings` function using `load_listings()` and a three-stage pipeline (price filter → size filter → keyword score). The generated scorer built a single blob string from `title + description + style_tags + colors` and used `in` for token matching.

**What I changed:** Removed `colors` from the scoring blob — color words like "black" or "white" appear so often that they dominated relevance scores and made unrelated items float to the top. Also tightened the size filter from `==` to `in` (substring) after realizing "M" wouldn't match "S/M" with an equality check.

---

### Instance 2 — Planning loop implementation

**Input given to Claude:** The Planning Loop section of `planning.md` (7 numbered conditional steps), the State Management table, and the Mermaid architecture diagram.

**What it produced:** A `run_agent()` function that closely matched the spec — session initialization, regex parsing, sequential tool calls with empty-check gates, and early returns on failure.

**What I changed:** The generated code passed `session` directly into `suggest_outfit(session, wardrobe)` rather than the unwrapped item dict. Changed to `suggest_outfit(session["selected_item"], wardrobe)` to keep tools decoupled from the session structure — consistent with the "tools receive plain values" principle from the State Management spec. Also added the `session["selected_item"] is session["search_results"][0]` identity assertion to the `__main__` block to make state continuity visible during testing.
