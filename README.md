# FitFindr — AI201 Project 2

FitFindr is a multi-tool AI agent that helps users find secondhand fashion listings and style them with their existing wardrobe.

The app starts from a natural-language shopping request, parses useful search filters, searches a mock resale dataset, selects the best matching item, suggests an outfit, and generates a short social-media-style fit card.

---

## Demo Summary

A complete happy-path interaction looks like this:

```text
User query: "platform sneakers size 8 under $60"
```

The agent then runs this tool chain:

```text
parse_query()
  -> search_listings(description="platform sneakers", size="8", max_price=60.0)
  -> suggest_outfit(new_item=selected_listing, wardrobe=example_wardrobe)
  -> create_fit_card(outfit=outfit_suggestion, new_item=selected_listing)
```

The final UI displays three outputs:

1. Top listing found
2. Outfit idea
3. Fit card caption

A no-results interaction, such as:

```text
designer ballgown size XXS under $5
```

stops after `search_listings()` and returns a specific message telling the user to broaden keywords, remove the size filter, or increase the budget.

---

## Required Tool Inventory

### Tool 1: `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`

**Purpose:** Searches the mock secondhand listings dataset for items matching the user's requested item description, optional size, and optional maximum price.

**Inputs:**

- `description` (`str`): The cleaned search phrase, such as `"vintage graphic tee"`, `"platform sneakers"`, or `"black combat boots"`.
- `size` (`str | None`): Optional size filter, such as `"M"`, `"8"`, `"US 8"`, or `"W30"`. If `None`, size is not used as a filter.
- `max_price` (`float | None`): Optional price ceiling. If provided, listings above this price are skipped.

**Return value:**

Returns a `list[dict]` sorted by relevance. Each dictionary is one listing from `data/listings.json` and includes:

- `id`
- `title`
- `description`
- `category`
- `style_tags`
- `size`
- `condition`
- `price`
- `colors`
- `brand`
- `platform`

If no listing matches, the tool returns an empty list `[]`.

**Failure behavior:**

- If no meaningful keywords are provided, it returns `[]`.
- If no listings match the filters, it returns `[]`.
- The planning loop detects the empty list and stops before calling the outfit or fit-card tools.

---

### Tool 2: `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

**Purpose:** Suggests 1–2 practical outfits using the selected secondhand listing and the user's wardrobe.

**Inputs:**

- `new_item` (`dict`): The selected listing dictionary returned by `search_listings()`. This is usually `session["selected_item"]`.
- `wardrobe` (`dict`): A wardrobe object containing an `items` list. Each wardrobe item may include fields like `name`, `category`, `colors`, `style_tags`, and `notes`.

**Return value:**

Returns a non-empty `str` containing outfit advice. With the example wardrobe, the output references specific wardrobe pieces by name. With an empty wardrobe, it gives general styling advice for bottoms, shoes, layers, and accessories.

**Failure behavior:**

- If `new_item` is missing, it returns a clear message saying a selected listing is needed.
- If the wardrobe is empty, it does not crash; it gives general styling guidance.
- If the Groq API key is missing or the API call fails, it uses deterministic fallback outfit logic.

---

### Tool 3: `create_fit_card(outfit: str, new_item: dict) -> str`

**Purpose:** Turns the outfit suggestion and selected listing into a short shareable thrift-find caption.

**Inputs:**

- `outfit` (`str`): The outfit suggestion returned by `suggest_outfit()`.
- `new_item` (`dict`): The same selected listing dictionary that was passed into `suggest_outfit()`.

**Return value:**

Returns a `str` caption, usually 2–4 sentences, that mentions the item name, price, resale platform, and outfit vibe.

**Failure behavior:**

- If `outfit` is empty, it returns a message saying an outfit suggestion is needed before a fit card can be created.
- If `new_item` is missing, it returns a message saying a selected listing is needed.
- If the Groq API key is missing or the API call fails, it uses a deterministic caption fallback.

---

## Multi-Step Workflow End to End

The main agent entry point is `run_agent(query: str, wardrobe: dict) -> dict` in `agent.py`.

For a happy-path query like:

```text
vintage graphic tee under $30
```

FitFindr does the following:

1. `parse_query()` extracts `description="vintage graphic tee"`, `size=None`, and `max_price=30.0`.
2. `search_listings()` searches the dataset and returns matching listings under $30.
3. The agent stores the top result as `session["selected_item"]`.
4. `suggest_outfit()` receives that exact selected listing plus the wardrobe.
5. The agent stores the outfit text as `session["outfit_suggestion"]`.
6. `create_fit_card()` receives the outfit text and the same selected listing.
7. The UI displays the listing, outfit idea, and fit card.

This proves all three required tools are called within one interaction.

---

## Planning Loop Conditional Logic

The planning loop is linear when everything succeeds, but it includes conditional checks that change the path when something goes wrong.

```text
1. Start session state.
2. If the query is empty, set an error and stop.
3. Parse the query into search parameters.
4. Call search_listings().
5. If search results are empty, set a no-results error and stop.
6. Otherwise, select the top listing.
7. Call suggest_outfit() with the selected listing and wardrobe.
8. If the outfit suggestion is empty, set an error and stop.
9. Call create_fit_card() with the outfit suggestion and selected listing.
10. Return the completed session.
```

The important adaptive behavior is that the agent does **not** call all tools unconditionally. For example, if `search_listings()` returns `[]`, the agent does not call `suggest_outfit()` or `create_fit_card()`, because there is no valid listing to style.

Concrete no-results example:

```text
Query: designer ballgown size XXS under $5
Result: no listings found
Agent response: I couldn't find any listings for 'designer ballgown' with filters (size XXS, under $5.00). Try broader keywords, removing the size filter, or increasing the budget.
```

---

## State Management Across Tool Calls

FitFindr uses a session dictionary as the single source of truth for one interaction.

```python
{
    "query": ...,              # original user text
    "parsed": ...,             # description, size, max_price
    "search_results": ...,     # list of listing dictionaries
    "selected_item": ...,      # top listing chosen from search_results
    "wardrobe": ...,           # current wardrobe object
    "outfit_suggestion": ...,  # text from suggest_outfit
    "fit_card": ...,           # text from create_fit_card
    "error": ...,              # error message if the loop stopped early
}
```

State flows forward like this:

```text
search_listings returns search_results
  -> agent selects search_results[0]
  -> selected_item is stored in session["selected_item"]
  -> selected_item is passed into suggest_outfit
  -> outfit_suggestion is stored in session["outfit_suggestion"]
  -> outfit_suggestion and selected_item are passed into create_fit_card
  -> fit_card is stored in session["fit_card"]
```

The user does not need to re-enter the selected listing or outfit. Each tool receives the previous tool's output from session state.

---

## Error Handling by Tool

| Tool / Step | Specific failure mode | Agent behavior |
|---|---|---|
| `parse_query()` / UI guard | User submits an empty or whitespace-only query | The UI returns: `Please describe what kind of item you want to find.` |
| `search_listings()` | No listing matches the description, size, and price filters | The agent sets `session["error"]` and tells the user to broaden keywords, remove the size filter, or increase the budget. |
| `search_listings()` | Search is too broad or synonym-only | The search requires at least one exact user token to appear in the listing, preventing loose matches like white sneakers for black combat boots. |
| `suggest_outfit()` | `new_item` is missing | The tool returns: `I need a selected listing before I can suggest an outfit.` |
| `suggest_outfit()` | Wardrobe is empty | The tool returns general styling advice instead of pretending it knows the user's closet. |
| `suggest_outfit()` | Groq API is unavailable | The tool uses deterministic fallback styling logic. |
| `create_fit_card()` | Outfit text is missing | The tool returns: `I need an outfit suggestion before I can create a fit card.` |
| `create_fit_card()` | Selected item is missing | The tool returns: `I need a selected listing before I can create a fit card.` |
| `create_fit_card()` | Groq API is unavailable | The tool uses a deterministic caption fallback. |

Concrete failure tested:

```text
black combat boots size 8 under $60
```

The dataset did not contain a valid black combat boot in size 8 under $60. The agent returned no result instead of incorrectly using a white sneaker or a tan boot. This was intentional so the agent would not hallucinate a match.

---

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional: create a `.env` file for Groq.

```bash
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

The app still works without a Groq key because the styling and caption tools include fallback behavior.

---

## Run the Agent from the Command Line

```bash
python agent.py
```

This runs a happy-path test and a no-results test.

---

## Run the Gradio App

```bash
python app.py
```

Then open the local URL printed in the terminal, usually:

```text
http://127.0.0.1:7860
```

Try these sample queries:

```text
vintage graphic tee under $30
platform sneakers size 8 under $60
designer ballgown size XXS under $5
```

---

## Run Tests

```bash
pytest
```

Current test coverage includes:

- query parsing
- search results
- no-results behavior
- empty wardrobe handling
- fit-card guardrails
- full happy-path agent loop
- full no-results agent loop

Latest local result:

```text
7 passed
```

---

## Spec Reflection

One way the spec helped was that it forced the project into three clear tools with defined interfaces. That made it easier to test each function independently before wiring them into the full planning loop.

One divergence from the initial plan was the search implementation. Instead of using an LLM to search listings, I made `search_listings()` deterministic with keyword matching, synonym expansion, size filtering, price filtering, and relevance scoring. I chose this because search should be reliable and testable, while the LLM is more useful for creative styling and caption generation.

---

## AI Usage Transparency

AI assistance was used during planning, implementation, and debugging, but the code was reviewed and tested against the project spec.

### Instance 1: Tool implementation planning

I directed AI assistance to help turn the Project 2 requirements into a concrete plan for the three tools: `search_listings`, `suggest_outfit`, and `create_fit_card`. I reviewed the generated plan against the rubric and kept the required tool names, inputs, outputs, failure behavior, and state-passing design.

### Instance 2: Search debugging and revision

I directed AI assistance to help debug search relevance after the query `black combat boots size 8 under $60` returned poor matches like tan Chelsea boots, white sneakers, and black jeans. I reviewed the outputs manually, identified that size matching and synonym matching were too loose, and revised the implementation so numeric sizes match more strictly and synonym-only results are filtered out.

### Instance 3: Agent loop and tests

I directed AI assistance to help structure the `run_agent()` planning loop and write tests. I reviewed the generated code by running the Gradio app, testing happy-path and no-results queries, and running `pytest`. I also revised behavior so the agent stops early on no-results instead of calling the outfit and fit-card tools with invalid state.

---

## Files

```text
app.py                  Gradio UI
agent.py                Planning loop and session state
tools.py                Agent tools
planning.md             Project planning document
data/listings.json      Mock secondhand listings
data/wardrobe_schema.json
utils/data_loader.py    Dataset loading helpers
tests/test_fitfindr.py  Automated tests
```
