"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)

# Common words that do not help search.
# Example: in "I want a vintage graphic tee", words like "I", "want", and "a"
# add noise. We remove them so the search focuses on "vintage", "graphic", "tee".
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "for", "from", "get", "i",
    "in", "is", "it", "looking", "me", "of", "on", "or", "out", "show",
    "some", "the", "to", "under", "want", "with", "would", "you", "what",
    "whats",
}


# Basic synonym expansion.
# The dataset might say "shoes", while the user says "sneakers".
# Or the listing might say "tee", while the user says "shirt".
# This makes our search feel smarter without needing an LLM.
_SYNONYMS = {
    "tee": {"tee", "tshirt", "t-shirt", "shirt", "top"},
    "tshirt": {"tee", "tshirt", "t-shirt", "shirt", "top"},

    "sneaker": {"sneaker", "sneakers", "shoe", "shoes"},
    "sneakers": {"sneaker", "sneakers", "shoe", "shoes"},

    "boot": {"boot", "boots", "shoe", "shoes"},
    "boots": {"boot", "boots", "shoe", "shoes"},

    "jacket": {"jacket", "outerwear", "coat"},

    "jeans": {"jeans", "denim", "bottoms", "pants"},
    "pants": {"pants", "bottoms", "trousers", "jeans"},

    "skirt": {"skirt", "bottoms"},
}


def _tokenize(text: str | None) -> set[str]:
    """
    Turn text into searchable lowercase tokens.

    Example:
        "Vintage graphic tee under $30!"
    becomes something like:
        {"vintage", "graphic", "tee", "tshirt", "shirt", "top", "30"}

    Why this matters:
    The search tool compares the user's query tokens against listing tokens.
    More overlap = more relevant result.
    """
    if not text:
        return set()

    # Lowercase makes matching case-insensitive.
    # The regex keeps letters/numbers and hyphenated words like "wide-leg".
    raw_tokens = set(
        re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower().replace("'", ""))
    )

    # Start with the original tokens.
    expanded_tokens = set(raw_tokens)

    # Add synonyms so "tee" can also match "shirt", "top", etc.
    for token in raw_tokens:
        expanded_tokens.update(_SYNONYMS.get(token, set()))

    # Remove stopwords and tiny useless tokens.
    return {
        token
        for token in expanded_tokens
        if token not in _STOPWORDS and len(token) > 1
    }
def _basic_tokens(text: str | None) -> set[str]:
    """
    Turn text into lowercase tokens without synonym expansion.

    Why this exists:
    _tokenize() expands synonyms, which is useful for scoring.
    But search still needs at least one exact user word match so it does not
    return loose results like "white sneakers" for "black combat boots".
    """
    if not text:
        return set()

    raw_tokens = set(
        re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower().replace("'", ""))
    )

    return {
        token
        for token in raw_tokens
        if token not in _STOPWORDS and len(token) > 1
    }

def _listing_text(listing: dict) -> str:
    """
    Combine all searchable fields from one listing into one string.

    Why this matters:
    A listing's useful words are spread across title, description, category,
    style tags, colors, brand, etc. Search should look at all of them, not just
    the title.
    """
    parts = [
        listing.get("title", ""),
        listing.get("description", ""),
        listing.get("category", ""),
        listing.get("size", ""),
        listing.get("condition", ""),
        listing.get("brand") or "",
        listing.get("platform", ""),
    ]

    # style_tags and colors are lists, so we add their words too.
    parts.extend(listing.get("style_tags", []))
    parts.extend(listing.get("colors", []))

    return " ".join(str(part) for part in parts if part)


def _size_matches(listing_size: str | None, requested_size: str | None) -> bool:
    """
    Flexible size matching for M, S/M, US 8, W30 L30, etc.

    Good matches:
        requested "M" -> listing "S/M"
        requested "8" -> listing "US 8"
        requested "W30" -> listing "W30 L30"

    Bad matches we prevent:
        requested "8" -> listing "US 8.5"
        requested "8" -> listing "W28"
    """

    if not requested_size:
        return True

    if not listing_size:
        return False

    listing_raw = listing_size.lower()
    listing_compact = listing_raw.replace(" ", "")
    requested = requested_size.lower().replace(" ", "")

    # Numeric sizes need strict standalone matching.
    # Use the raw listing text so "US 8" can match, but "US 8.5" and "W28" do not.
    if requested.isdigit():
        return bool(
            re.search(
                rf"(?<![a-z0-9.]){re.escape(requested)}(?![0-9.])",
                listing_raw,
            )
        )

    # Letter sizes need separator-based matching.
    # This lets "M" match "S/M" without matching random words.
    if requested in {"xxs", "xs", "s", "m", "l", "xl", "xxl"}:
        size_parts = re.split(r"[/,()\-\s]+", listing_compact)
        return requested in size_parts

    # Structured sizes like "US 8" or "W30".
    # These are safe to compact-match because they carry a prefix.
    if requested.startswith("us") or requested.startswith("w"):
        return requested in listing_compact

    return requested == listing_compact

# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    This is deterministic search, not an LLM call.
    Why? Search should be reliable, testable, and cheap.
    The LLM can style the result later, but item retrieval should be predictable.
    """

    # Convert the user's search description into useful keywords.
    # Example: "vintage graphic tee" -> {"vintage", "graphic", "tee", "shirt", "top"}
    query_tokens = _tokenize(description)
    query_exact_tokens = _basic_tokens(description)

    # If the query has no meaningful words, there is nothing to search for.
    if not query_tokens:
        return []

    # We store tuples of:
    #   (score, price, listing)
    #
    # score decides relevance.
    # price is included so cheaper items win ties.
    # listing is the original dictionary we return later.
    scored_results: list[tuple[int, float, dict]] = []

    # Load every listing from data/listings.json.
    for listing in load_listings():
        price = float(listing.get("price", 0))

        # Price filter:
        # If the user said "under $30", max_price is 30.
        # Anything above that gets skipped immediately.
        if max_price is not None and price > max_price:
            continue

        # Size filter:
        # Uses our helper so "M" can match "S/M", and "8" can match "US 8".
        if not _size_matches(listing.get("size"), size):
            continue

        # Combine title, description, tags, colors, brand, etc. into searchable text.
        searchable_text = _listing_text(listing)

        # Tokenize the listing too, so query and listing can be compared.
        listing_exact_tokens = _basic_tokens(searchable_text)
        listing_tokens = _tokenize(searchable_text)

        # Strict gate:
        # At least one real user word must appear in the listing.
        # This prevents synonym-only matches from being treated as relevant.
        if query_exact_tokens and not (query_exact_tokens & listing_exact_tokens):
            continue

        # Keyword overlap is the core relevance signal.
        # More shared tokens = better match.
        overlap = query_tokens & listing_tokens

        # Each overlapping keyword is worth 3 points.
        # We use 3 instead of 1 so overlap matters more than tiny bonuses.
        score = len(overlap) * 3

        description_lower = description.lower().strip()
        text_lower = searchable_text.lower()
        title_lower = listing.get("title", "").lower()

        # Big bonus if the exact cleaned query appears in the listing text.
        # Example: "graphic tee" appearing directly is stronger than random overlap.
        if description_lower and description_lower in text_lower:
            score += 6

        # Bonus for specific common fashion phrases.
        # These phrases are stronger than individual words.
        important_phrases = [
            "graphic tee",
            "track jacket",
            "combat boots",
            "mary janes",
            "wide-leg",
            "midi skirt",
        ]

        for phrase in important_phrases:
            if phrase in description_lower and phrase in text_lower:
                score += 5

        # Bonus if a style tag directly appears in the query.
        # Tags are curated dataset labels, so they are high-signal.
        for tag in listing.get("style_tags", []):
            if tag.lower() in description_lower:
                score += 3

        # Small title bonus.
        # A title match should matter, but not overpower the full listing context.
        if any(token in title_lower for token in query_tokens):
            score += 2

        # Drop irrelevant results.
        # Score 0 means there was no useful match.
        if score > 0:
            scored_results.append((score, price, listing))

    # Sort by:
    #   1. Highest score first
    #   2. Lowest price second
    #   3. Title alphabetically for stable results
    scored_results.sort(
        key=lambda row: (-row[0], row[1], row[2].get("title", ""))
    )

    # Return only the listing dictionaries, not the internal scoring info.
    return [listing for _, _, listing in scored_results]

# Neutral colors are easy to pair with most outfits.
# We use this in the fallback outfit logic when there is no LLM response.
_NEUTRALS = {
    "black", "white", "grey", "gray", "tan", "brown",
    "cream", "navy", "denim", "blue", "indigo",
}


def _call_groq(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
) -> str | None:
    """
    Try to call Groq and return the model's text response.

    Why this helper exists:
    Both suggest_outfit() and create_fit_card() need the LLM.
    Instead of duplicating API code twice, we put it here.

    Why it returns None on failure:
    Missing API keys and network/API errors should not crash the whole app.
    If Groq is unavailable, the public tool functions can use fallback logic.
    """
    try:
        client = _get_groq_client()

        # Default to a strong general-purpose Groq model.
        # This can be overridden in .env with GROQ_MODEL.
        model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=450,
        )

        return response.choices[0].message.content.strip()

    except Exception:
        # In a production app, we might log the exception.
        # For this class project, failing gracefully is better than crashing.
        return None


def _format_wardrobe_item(item: dict) -> str:
    """
    Turn one wardrobe item dictionary into readable text for the LLM prompt.

    Why this matters:
    LLMs respond better when structured data is converted into clear context.
    """
    name = item.get("name", "Unknown item")
    category = item.get("category", "item")
    colors = ", ".join(item.get("colors", [])) or "unknown colors"
    tags = ", ".join(item.get("style_tags", [])) or "no style tags"
    notes = item.get("notes")

    if notes:
        return f"{name} ({category}; colors: {colors}; style: {tags}; notes: {notes})"

    return f"{name} ({category}; colors: {colors}; style: {tags})"


def _pick_items_by_category(items: list[dict], category: str) -> list[dict]:
    """
    Return wardrobe items from one category.

    Why this exists:
    The fallback outfit builder needs to find bottoms, shoes, layers, etc.
    """
    return [item for item in items if item.get("category") == category]


def _color_score(new_item: dict, wardrobe_item: dict) -> int:
    """
    Score how easily a wardrobe item pairs with the new item by color.

    2 points: shared color
    1 point: one item has a neutral color
    0 points: no obvious color relationship

    Why this exists:
    The fallback styling should make decent choices without an LLM.
    """
    new_colors = {color.lower() for color in new_item.get("colors", [])}
    wardrobe_colors = {color.lower() for color in wardrobe_item.get("colors", [])}

    if new_colors & wardrobe_colors:
        return 2

    if new_colors & _NEUTRALS or wardrobe_colors & _NEUTRALS:
        return 1

    return 0


def _best_color_match(new_item: dict, items: list[dict]) -> dict | None:
    """
    Pick the wardrobe item with the best color compatibility.

    Why this exists:
    It keeps fallback outfit selection simple and reusable.
    """
    if not items:
        return None

    return sorted(
        items,
        key=lambda item: _color_score(new_item, item),
        reverse=True,
    )[0]
# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    This tool uses the LLM when possible because outfit advice is natural-language
    generation. But it also has a deterministic fallback so the app still works
    without a Groq API key.
    """

    # Guardrail:
    # This tool depends on a selected listing from search_listings().
    # If the agent calls it without an item, return a useful message instead
    # of crashing.
    if not new_item:
        return "I need a selected listing before I can suggest an outfit."

    # Safely pull the wardrobe items list.
    # If wardrobe is malformed or empty, this becomes an empty list.
    wardrobe_items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    # Summarize the new item for the LLM.
    # LLMs do better when we give structured, compact context instead of a raw dict.
    item_summary = (
        f"{new_item.get('title', 'this item')} | "
        f"category: {new_item.get('category', 'unknown')} | "
        f"colors: {', '.join(new_item.get('colors', [])) or 'unknown'} | "
        f"style tags: {', '.join(new_item.get('style_tags', [])) or 'none'} | "
        f"price: ${float(new_item.get('price', 0)):.2f} | "
        f"platform: {new_item.get('platform', 'unknown')}"
    )

    # Case 1: user has wardrobe items.
    # We ask the LLM to use specific named pieces, because that proves the agent
    # is actually using state from the wardrobe tool/data.
    if wardrobe_items:
        wardrobe_text = "\n".join(
            f"- {_format_wardrobe_item(item)}"
            for item in wardrobe_items
        )

        user_prompt = f"""
New item:
{item_summary}

User wardrobe:
{wardrobe_text}

Suggest 1–2 complete outfits using the new item and named pieces from the wardrobe.
Be practical, specific, and concise. Mention why the pieces work together.
""".strip()

    # Case 2: empty wardrobe.
    # The tool should still help the user. It just gives general advice instead
    # of pretending it knows their closet.
    else:
        user_prompt = f"""
New item:
{item_summary}

The user has not entered any wardrobe items yet.
Suggest general styling advice: what bottoms, shoes, layers, and accessories would pair well.
Be practical, specific, and concise.
""".strip()

    # Try the LLM.
    # Temperature 0.6 = creative enough for styling, but not totally chaotic.
    llm_response = _call_groq(
        system_prompt="You are FitFindr, a stylish but practical secondhand fashion assistant.",
        user_prompt=user_prompt,
        temperature=0.6,
    )

    # If Groq works, return the polished LLM answer.
    if llm_response:
        return llm_response

    # If Groq is missing/fails, return deterministic fallback advice.
    return _fallback_outfit(new_item, wardrobe_items)

def _fallback_outfit(new_item: dict, wardrobe_items: list[dict]) -> str:
    """
    Deterministic styling fallback for demos/tests without a Groq key.

    Why this exists:
    The project should still run locally even before the API key is configured.
    The fallback is simpler than an LLM, but it proves the tool chain works.
    """

    title = new_item.get("title", "this thrifted piece")
    category = new_item.get("category")
    colors = ", ".join(new_item.get("colors", [])) or "its main color"
    style_tags = list(new_item.get("style_tags", []))
    vibe = ", ".join(style_tags[:3]) or "secondhand"

    # Empty wardrobe path:
    # We cannot reference named wardrobe pieces, so we give general styling advice.
    if not wardrobe_items:
        return (
            f"Style {title} around the {vibe} vibe. "
            f"Since it has {colors}, pair it with clean basics, one grounding neutral, "
            "simple shoes, and an accessory that repeats a color from the item."
        )

    # Group wardrobe items by category.
    # This lets us build a complete outfit instead of randomly picking pieces.
    tops = _pick_items_by_category(wardrobe_items, "tops")
    bottoms = _pick_items_by_category(wardrobe_items, "bottoms")
    outerwear = _pick_items_by_category(wardrobe_items, "outerwear")
    shoes = _pick_items_by_category(wardrobe_items, "shoes")
    accessories = _pick_items_by_category(wardrobe_items, "accessories")

    outfit_parts: list[str] = []

    # If the new item is not a top, pick a top from the wardrobe.
    if category != "tops":
        top = _best_color_match(new_item, tops)
        if top:
            outfit_parts.append(top["name"])

    # If the new item is not bottoms, pick bottoms from the wardrobe.
    if category != "bottoms":
        bottom = _best_color_match(new_item, bottoms)
        if bottom:
            outfit_parts.append(bottom["name"])

    # If the new item is not outerwear, add a layer if available.
    if category != "outerwear":
        layer = _best_color_match(new_item, outerwear)
        if layer:
            outfit_parts.append(layer["name"])

    # If the new item is not shoes, pick shoes from the wardrobe.
    if category != "shoes":
        shoe = _best_color_match(new_item, shoes)
        if shoe:
            outfit_parts.append(shoe["name"])

    # Accessories are optional but make the suggestion feel more complete.
    accessory = _best_color_match(new_item, accessories)
    if accessory:
        outfit_parts.append(accessory["name"])

    # If the wardrobe somehow had items but none fit our categories,
    # still return something useful.
    if not outfit_parts:
        return (
            f"Use {title} as the statement piece and keep the rest of the outfit simple. "
            f"The {colors} color story and {vibe} details should carry the look."
        )

    return (
        f"Outfit idea: wear {title} with "
        + ", ".join(outfit_parts)
        + ". "
        f"The {colors} color story keeps it grounded, while the {vibe} details "
        "give the fit a clear point of view."
    )

# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    This is the final tool in the chain:
        search_listings() -> suggest_outfit() -> create_fit_card()

    It takes the outfit suggestion and turns it into something the user could
    actually post as an OOTD/thrift-find caption.
    """

    # Guardrail:
    # If there is no outfit suggestion, we cannot make a fit card.
    # Returning a message is better than crashing the agent.
    if not outfit or not outfit.strip():
        return "I need an outfit suggestion before I can create a fit card."

    # Guardrail:
    # The caption needs listing details like title, price, and platform.
    if not new_item:
        return "I need a selected listing before I can create a fit card."

    # Pull listing details safely.
    title = new_item.get("title", "this thrifted find")
    price = float(new_item.get("price", 0))
    platform = new_item.get("platform", "a resale platform")

    # Build a clear prompt for the LLM.
    # We include exact constraints so the output is short and usable.
    user_prompt = f"""
Create a short OOTD/thrift-find caption.

Item: {title}
Price: ${price:.2f}
Platform: {platform}
Outfit idea: {outfit}

Requirements:
- 2–4 sentences
- casual and authentic, not ad-copy
- mention the item name, price, and platform naturally once
- capture the outfit vibe in specific terms
""".strip()

    # Higher temperature here is fine because captions can be creative.
    # Search should be predictable, but captions can have more personality.
    llm_response = _call_groq(
        system_prompt="You write casual, specific, social-media-ready outfit captions.",
        user_prompt=user_prompt,
        temperature=0.9,
    )

    # If Groq works, use the polished caption.
    if llm_response:
        return llm_response

    # Fallback:
    # If the API key fails, still return a usable caption.
    return (
        f"Found {title} for ${price:.2f} on {platform}, and it has that "
        "effortless but intentional thrift energy. "
        f"{outfit} "
        "This is the kind of piece that makes the whole fit look curated without trying too hard."
    )
