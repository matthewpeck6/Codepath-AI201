"""
app.py

Gradio interface for FitFindr.

Run with:
    python app.py

Then open the localhost URL shown in your terminal.
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Returns:
        (listing_text, outfit_suggestion, fit_card) — one string per output panel.
    """
    # ── Step 1: guard against empty query ─────────────────────────────────────
    if not user_query or not user_query.strip():
        return "Please enter a search query (e.g. 'vintage graphic tee under $30').", "", ""

    # ── Step 2: select wardrobe ────────────────────────────────────────────────
    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # ── Step 3: run agent ──────────────────────────────────────────────────────
    session = run_agent(user_query, wardrobe)

    # ── Step 4: handle error ───────────────────────────────────────────────────
    if session["error"] and session["fit_card"] is None:
        return session["error"], "", ""

    # ── Step 5: format outputs ─────────────────────────────────────────────────
    item = session["selected_item"]
    colors = ", ".join(item.get("colors", [])) or "—"
    tags = ", ".join(item.get("style_tags", [])) or "—"
    brand = item.get("brand") or "unbranded"
    listing_text = (
        f"🛍️  {item['title']}\n"
        f"─────────────────────────────\n"
        f"Price:     ${item['price']:.2f}\n"
        f"Platform:  {item['platform'].capitalize()}\n"
        f"Size:      {item['size']}\n"
        f"Condition: {item['condition'].capitalize()}\n"
        f"Brand:     {brand}\n"
        f"Colors:    {colors}\n"
        f"Vibe:      {tags}\n"
        f"─────────────────────────────\n"
        f"{item.get('description', '')}"
    )

    outfit = session["outfit_suggestion"] or ""
    fit_card = session["fit_card"] or session.get("error") or ""

    return listing_text, outfit, fit_card


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
