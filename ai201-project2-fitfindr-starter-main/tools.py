"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re
import json
import urllib.request

from utils.data_loader import load_listings

# ── LLM client ────────────────────────────────────────────────────────────────

def _call_llm(prompt: str, temperature: float = 0.7, max_tokens: int = 500) -> str:
    """
    Call the Anthropic Claude API directly via urllib (no SDK required).
    Falls back to a mock response if ANTHROPIC_API_KEY is not set, so that
    search_listings tests run without any API key.

    For Groq users: swap the URL, headers, and payload shape for Groq's
    /openai/v1/chat/completions endpoint and set GROQ_API_KEY instead.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GROQ_API_KEY")

    if not api_key:
        # No key available — return a clearly-labelled mock so LLM tools still
        # return a non-empty string and don't mask bugs in the planning loop.
        return (
            "[MOCK — no API key set] "
            f"Outfit suggestion for prompt starting with: {prompt[:80]!r}"
        )

    # Detect which key we have and route accordingly
    if os.environ.get("GROQ_API_KEY"):
        return _call_groq(prompt, temperature, max_tokens)
    else:
        return _call_anthropic(prompt, temperature, max_tokens)


def _call_anthropic(prompt: str, temperature: float, max_tokens: int) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def _call_groq(prompt: str, temperature: float, max_tokens: int) -> str:
    api_key = os.environ["GROQ_API_KEY"]
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for.
        size:        Size string, or None to skip size filtering.
                     Case-insensitive; a listing matches if its size field
                     *contains* the given string (e.g. "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Scoring: counts how many whitespace-split tokens from `description` appear
    (case-insensitive) in the combined text of title + description + style_tags.
    Listings scoring 0 are dropped.
    """
    listings = load_listings()

    # ── Step 1: hard filters ──────────────────────────────────────────────────
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # ── Step 2: keyword scoring ───────────────────────────────────────────────
    tokens = [t.lower() for t in description.split() if t]

    def _score(listing: dict) -> int:
        # Build one big searchable blob from text fields
        tags_text = " ".join(listing.get("style_tags", []))
        blob = (
            f"{listing['title']} {listing['description']} {tags_text}"
        ).lower()
        return sum(1 for tok in tokens if tok in blob)

    scored = [(listing, _score(listing)) for listing in listings]

    # ── Step 3: drop zero-score items and sort ────────────────────────────────
    matched = [(l, s) for l, s in scored if s > 0]
    matched.sort(key=lambda x: x[1], reverse=True)

    return [l for l, _ in matched]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions or general styling advice.
    """
    item_summary = (
        f"Item: {new_item['title']}\n"
        f"Category: {new_item['category']}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Description: {new_item.get('description', '')}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe → general styling advice
        prompt = (
            "You are a thrift-fashion stylist. A user just found this secondhand item:\n\n"
            f"{item_summary}\n\n"
            "They haven't told you what's in their wardrobe yet. "
            "Suggest 1–2 outfit ideas using common wardrobe staples that would pair well "
            "with this item. Be specific about the types of pieces, colors, and the overall "
            "vibe each outfit achieves. Keep it to 3–5 sentences total."
        )
    else:
        # Format wardrobe items into readable list
        wardrobe_lines = []
        for w in wardrobe_items:
            notes = f" ({w['notes']})" if w.get("notes") else ""
            colors = ", ".join(w.get("colors", []))
            wardrobe_lines.append(f"- {w['name']} [{colors}]{notes}")
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            "You are a thrift-fashion stylist. A user just found this secondhand item:\n\n"
            f"{item_summary}\n\n"
            "Their current wardrobe contains:\n"
            f"{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfit combinations using the new item and specific "
            "named pieces from their wardrobe above. Reference each wardrobe piece by name. "
            "Describe the overall vibe each outfit achieves. "
            "Keep it to 4–6 sentences total."
        )

    result = _call_llm(prompt, temperature=0.7, max_tokens=400)
    return result if result.strip() else "[No outfit suggestion returned]"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence Instagram/TikTok-style caption string.
        Returns a descriptive error string (no exception) if outfit is empty.
    """
    # ── Guard: empty outfit ───────────────────────────────────────────────────
    if not outfit or not outfit.strip():
        return "Couldn't generate a fit card — outfit details were missing."

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift app")

    prompt = (
        "You are writing an authentic OOTD (outfit of the day) caption for Instagram or TikTok. "
        "Make it sound like a real person sharing their thrift find — casual, specific, enthusiastic. "
        "NOT like a product description or ad copy.\n\n"
        f"The thrifted item: {title} — found on {platform} for ${price}\n\n"
        f"The outfit idea: {outfit}\n\n"
        "Write a 2–4 sentence caption that:\n"
        "- Mentions the item name, price, and platform naturally (once each)\n"
        "- Describes the outfit vibe in specific visual terms\n"
        "- Sounds casual and personal, like a real OOTD post\n"
        "- Does NOT use bullet points or headers — just flowing caption text\n\n"
        "Write only the caption, nothing else."
    )

    result = _call_llm(prompt, temperature=0.9, max_tokens=200)
    return result if result.strip() else "Couldn't generate a fit card — try again."


# ── Manual smoke tests (run with: python tools.py) ───────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=" * 60)
    print("TOOL 1: search_listings")
    print("=" * 60)

    results = search_listings("vintage graphic tee", size=None, max_price=50)
    print(f"\nTest A — 'vintage graphic tee' under $50: {len(results)} result(s)")
    if results:
        r = results[0]
        print(f"  Top result: {r['title']} — ${r['price']} ({r['platform']})")

    results_filtered = search_listings("graphic tee", size="M", max_price=25)
    print(f"\nTest B — 'graphic tee', size M, under $25: {len(results_filtered)} result(s)")
    for r in results_filtered:
        print(f"  {r['title']} | size: {r['size']} | ${r['price']}")

    results_empty = search_listings("designer ballgown", size="XXS", max_price=5)
    print(f"\nTest C — 'designer ballgown' XXS under $5: {len(results_empty)} result(s) (expect 0)")
    assert results_empty == [], f"Expected empty list, got {results_empty}"

    results_price = search_listings("jacket", size=None, max_price=10)
    print(f"\nTest D — 'jacket' under $10: {len(results_price)} result(s)")
    for r in results_price:
        assert r["price"] <= 10, f"Price filter failed: {r['price']}"
    print("  All prices ≤ $10 ✓")

    print("\n" + "=" * 60)
    print("TOOL 2: suggest_outfit")
    print("=" * 60)

    # Use first good search result as the new_item
    item = search_listings("vintage graphic tee", max_price=50)[0]
    print(f"\nItem: {item['title']}")

    print("\nTest A — with example wardrobe:")
    suggestion = suggest_outfit(item, get_example_wardrobe())
    print(f"  {suggestion[:200]}...")
    assert suggestion.strip(), "suggest_outfit returned empty string"

    print("\nTest B — with empty wardrobe:")
    suggestion_empty = suggest_outfit(item, get_empty_wardrobe())
    print(f"  {suggestion_empty[:200]}...")
    assert suggestion_empty.strip(), "suggest_outfit returned empty string for empty wardrobe"

    print("\n" + "=" * 60)
    print("TOOL 3: create_fit_card")
    print("=" * 60)

    print("\nTest A — empty outfit guard:")
    result = create_fit_card("", item)
    print(f"  '{result}'")
    assert "missing" in result.lower() or "couldn't" in result.lower()

    print("\nTest B — whitespace-only outfit guard:")
    result = create_fit_card("   ", item)
    print(f"  '{result}'")
    assert result.strip(), "Should return error string, not empty"

    print("\nTest C — real outfit input:")
    caption = create_fit_card(suggestion, item)
    print(f"  {caption}")
    assert caption.strip(), "create_fit_card returned empty string"

    print("\nTest D — run twice, verify variation:")
    caption2 = create_fit_card(suggestion, item)
    print(f"  Run 2: {caption2[:100]}...")
    if caption == caption2:
        print("  ⚠️  Outputs identical — consider increasing temperature")
    else:
        print("  ✓ Outputs differ (temperature working)")

    print("\n✅ All smoke tests passed.")
