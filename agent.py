"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
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
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }

# ── query parsing ────────────────────────────────────────────────────────────
def parse_query(query: str) -> dict:
    """
    Extract structured search parameters from a natural-language user query.

    The agent receives normal user text, but search_listings() needs:
        description, size, max_price

    Example:
        "black combat boots size 8 under $60"

    becomes:
        {
            "description": "black combat boots",
            "size": "8",
            "max_price": 60.0,
        }
    """

    # Keep the original query so we can safely fall back if cleaning gets weird.
    original_query = query.strip()

    # This is the working copy we will remove price/size phrases from.
    description = original_query

    max_price = None
    size = None

    # ------------------------------------------------------------
    # 1. Extract price
    # ------------------------------------------------------------
    # This regex allows:
    #   under $60
    #   under 60
    #   below $30
    #   less than 25
    #   max $50
    #   budget 40
    #
    # Important detail:
    # We allow optional spaces after the dollar sign:
    #   $60 and $ 60 both work.
    price_pattern = (
        r"(?:under|below|less than|max|maximum|budget)\s*"
        r"\$?\s*"
        r"(\d+(?:\.\d+)?)"
    )

    price_match = re.search(price_pattern, description, flags=re.IGNORECASE)

    if price_match:
        max_price = float(price_match.group(1))

        # Remove the whole phrase, not just the number.
        # Example:
        #   "black boots under $60" -> "black boots"
        description = re.sub(
            price_pattern,
            "",
            description,
            flags=re.IGNORECASE,
        )

    # ------------------------------------------------------------
    # 2. Extract size
    # ------------------------------------------------------------
    # This handles:
    #   size M
    #   size XL
    #   size 8
    #   US 8
    #   W30
    #
    # We do this after price so "under $60" does not confuse size parsing.
    size_patterns = [
        r"(?:in\s+)?size\s+([a-zA-Z]{1,3}|\d{1,2}|US\s*\d{1,2}|W\d{1,2})",
        r"\b(US\s*\d{1,2}|W\d{1,2})\b",
    ]

    for pattern in size_patterns:
        size_match = re.search(pattern, description, flags=re.IGNORECASE)

        if size_match:
            size = size_match.group(1).upper().replace(" ", "")

            # Normalize "US8" to "US 8" because listings may use that format.
            if size.startswith("US") and len(size) > 2:
                size = "US " + size[2:]

            # Remove the full size phrase from description.
            description = re.sub(
                pattern,
                "",
                description,
                flags=re.IGNORECASE,
            )
            break

    # ------------------------------------------------------------
    # 3. Clean description
    # ------------------------------------------------------------
    # Remove leftover punctuation and extra spaces.
    description = re.sub(r"[$,]", " ", description)
    description = re.sub(r"\s+", " ", description).strip()

    # Remove dangling shopping filter words if they somehow remain.
    # Example: "vintage graphic tee under" -> "vintage graphic tee"
    description = re.sub(
        r"\b(under|below|less than|max|maximum|budget|size)\b$",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip()

    # If cleaning deleted everything, fall back to original query.
    if not description:
        description = original_query

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }

# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop:
        1. Start session state
        2. Parse query into structured search parameters
        3. Search listings
        4. Stop early if no listings match
        5. Select the top listing
        6. Suggest an outfit
        7. Create a fit card
        8. Return the final session

    Why this function matters:
    The individual tools are useful alone, but the project is about an agent.
    This function is the agent brain that decides what happens next.
    """

    # Initialize session state.
    # This gives us one place to store every decision and tool result.
    session = _new_session(query, wardrobe)

    try:
        # Guardrail:
        # Empty queries should not go into search because they would return
        # meaningless results.
        if not query or not query.strip():
            session["error"] = "Please describe what kind of item you want to find."
            return session

        # Step 1: Parse the user's natural-language query.
        # Example:
        #   "black combat boots size 8 under $60"
        # becomes:
        #   {"description": "black combat boots", "size": "8", "max_price": 60.0}
        parsed = parse_query(query)
        session["parsed"] = parsed

        # Step 2: Search listings using the structured parameters.
        results = search_listings(
            description=parsed["description"],
            size=parsed["size"],
            max_price=parsed["max_price"],
        )
        session["search_results"] = results

        # Step 3: Handle no-results early.
        # This is important because suggest_outfit() needs a selected item.
        if not results:
            filters_used = []

            if parsed["size"]:
                filters_used.append(f"size {parsed['size']}")

            if parsed["max_price"] is not None:
                filters_used.append(f"under ${parsed['max_price']:.2f}")

            filter_text = f" with filters ({', '.join(filters_used)})" if filters_used else ""

            session["error"] = (
                f"I couldn't find any listings for '{parsed['description']}'{filter_text}. "
                "Try broader keywords, removing the size filter, or increasing the budget."
            )
            return session

        # Step 4: Select top result.
        # search_listings() already sorts by relevance, so index 0 is the best match.
        selected_item = results[0]
        session["selected_item"] = selected_item

        # Step 5: Suggest outfit using the selected item and wardrobe state.
        outfit_suggestion = suggest_outfit(
            new_item=selected_item,
            wardrobe=wardrobe,
        )
        session["outfit_suggestion"] = outfit_suggestion

        # Guardrail:
        # If outfit generation somehow returns nothing, stop before fit card.
        if not outfit_suggestion or not outfit_suggestion.strip():
            session["error"] = "I found an item, but couldn't generate an outfit suggestion."
            return session

        # Step 6: Create final fit card.
        fit_card = create_fit_card(
            outfit=outfit_suggestion,
            new_item=selected_item,
        )
        session["fit_card"] = fit_card

        return session

    except Exception as exc:
        # Last-resort safety net.
        # A production app might log this, but for this project we return it
        # cleanly so the UI can display a helpful message instead of crashing.
        session["error"] = f"Something went wrong while running the agent: {exc}"
        return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
