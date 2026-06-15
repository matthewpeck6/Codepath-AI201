"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

# Size tokens: XS, S, M, L, XL, XXL, XXS, S/M, M/L, or waist sizes like W28
_SIZE_PATTERN = re.compile(
    r"\b(XXS|XXL|XS|XL|S/M|M/L|S|M|L|W\d{2}(?:\s*L\d{2})?)\b",
    re.IGNORECASE,
)

# Price: "under $30", "under 30", "$30", "< $30", "max $30"
_PRICE_PATTERN = re.compile(
    r"(?:under|max|<|up\s+to)?\s*\$?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Words to strip when building the description (non-content filter words)
_STOP_WORDS = {
    "under", "max", "size", "for", "a", "an", "the", "in", "at",
    "looking", "i'm", "im", "want", "find", "me", "something",
}


def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.

    Strategy: regex-first (fast, no API call required).
    - Size: first token matching _SIZE_PATTERN
    - Price: first number following a price trigger word ("under", "$", etc.)
    - Description: remaining words after removing size/price tokens and stop words

    Returns a dict with keys: description (str), size (str|None), max_price (float|None)
    """
    # ── Extract size ──────────────────────────────────────────────────────────
    size_match = _SIZE_PATTERN.search(query)
    size = size_match.group(0).upper() if size_match else None

    # ── Extract max_price ─────────────────────────────────────────────────────
    max_price = None
    # Look for explicit price patterns like "under $30" or "under 30"
    price_trigger = re.search(
        r"(?:under|max|<|up\s+to)\s*\$?\s*(\d+(?:\.\d+)?)", query, re.IGNORECASE
    )
    if price_trigger:
        max_price = float(price_trigger.group(1))
    else:
        # Bare "$30" with no trigger word
        bare_dollar = re.search(r"\$(\d+(?:\.\d+)?)", query)
        if bare_dollar:
            max_price = float(bare_dollar.group(1))

    # ── Build description ─────────────────────────────────────────────────────
    # Remove the price portion and size token from the query, then clean up
    clean = query
    if price_trigger:
        clean = clean[:price_trigger.start()] + clean[price_trigger.end():]
    elif bare_dollar:
        clean = clean[:bare_dollar.start()] + clean[bare_dollar.end():]
    if size_match:
        # Remove just the size token (not surrounding words)
        clean = re.sub(r"\bsize\b", "", clean, flags=re.IGNORECASE)
        clean = _SIZE_PATTERN.sub("", clean)

    # Tokenize, drop stop words and punctuation noise, rejoin
    tokens = [
        t.strip(".,!?;:'\"")
        for t in clean.split()
        if t.strip(".,!?;:'\"").lower() not in _STOP_WORDS
        and t.strip(".,!?;:'\"")
    ]
    description = " ".join(tokens).strip() or query  # fallback to full query

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Steps:
        1  Initialize session
        2  Parse query → description, size, max_price
        3  Call search_listings → if empty, set error and return early
        4  Select top result as selected_item
        5  Call suggest_outfit → if empty, set error and return early
        6  Call create_fit_card → if error string returned, propagate
        7  Return completed session
    """
    # ── Step 1: initialize ────────────────────────────────────────────────────
    session = _new_session(query, wardrobe)

    # ── Step 2: parse query ───────────────────────────────────────────────────
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # ── Step 3: search ────────────────────────────────────────────────────────
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    if not results:
        session["error"] = (
            f"No listings found matching '{query}'. "
            "Try broadening your search — remove the size or price filter, "
            "or use more general keywords."
        )
        return session

    # ── Step 4: select top result ─────────────────────────────────────────────
    session["selected_item"] = results[0]

    # ── Step 5: suggest outfit ────────────────────────────────────────────────
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    if not outfit or not outfit.strip():
        session["error"] = (
            "We found a great item but couldn't generate outfit ideas right now. "
            "Try again in a moment."
        )
        return session

    # ── Step 6: create fit card ───────────────────────────────────────────────
    fit_card = create_fit_card(outfit, session["selected_item"])
    session["fit_card"] = fit_card

    # create_fit_card returns an error string (not None) on failure
    error_phrases = ["couldn't generate", "outfit details were missing"]
    if not fit_card or any(p in fit_card.lower() for p in error_phrases):
        session["error"] = (
            f"Your outfit idea is ready but we couldn't format the fit card. "
            f"Here's the suggestion:\n\n{outfit}"
        )
        # Don't return early — outfit_suggestion is still valuable to the caller

    # ── Step 7: return session ────────────────────────────────────────────────
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=" * 60)
    print("=== Happy path: graphic tee ===")
    print("=" * 60)
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Parsed:   {session['parsed']}")
        print(f"Found:    {session['selected_item']['title']} — ${session['selected_item']['price']}")
        print(f"Platform: {session['selected_item']['platform']}")
        print(f"\nOutfit: {session['outfit_suggestion'][:200]}...")
        print(f"\nFit card: {session['fit_card'][:200]}...")

    # Verify state continuity
    assert session["selected_item"] is session["search_results"][0], \
        "selected_item should be the exact same dict as search_results[0]"
    print("\n✅ State continuity check passed (selected_item is search_results[0])")

    print("\n\n" + "=" * 60)
    print("=== No-results path ===")
    print("=" * 60)
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"error:         {session2['error']}")
    print(f"fit_card:      {session2['fit_card']}")
    print(f"outfit:        {session2['outfit_suggestion']}")
    assert session2["error"] is not None, "Expected error for no-results query"
    assert session2["fit_card"] is None, "fit_card should be None on early exit"
    assert session2["outfit_suggestion"] is None, "outfit_suggestion should be None on early exit"
    print("\n✅ No-results path: error set, fit_card=None, outfit_suggestion=None")

    print("\n\n" + "=" * 60)
    print("=== Size + price parsing ===")
    print("=" * 60)
    session3 = run_agent(
        query="90s track jacket in size M under $40",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Parsed: {session3['parsed']}")
    assert session3['parsed']['size'] == 'M', f"Expected size M, got {session3['parsed']['size']}"
    assert session3['parsed']['max_price'] == 40.0, f"Expected 40.0, got {session3['parsed']['max_price']}"
    print("✅ Query parsing correct")
