# FitFindr — AI201 Project 2

FitFindr is a multi-tool AI agent that helps users find secondhand fashion listings and style them with their existing wardrobe.

The agent takes a natural-language shopping request, searches a mock resale dataset, selects the best matching item, suggests an outfit, and creates a short social-media-style fit card.

---

## What the Agent Does

Example query:

```text
vintage graphic tee under $30
```

FitFindr will:

1. Parse the query into structured search filters.
2. Search the mock secondhand listings dataset.
3. Select the most relevant listing.
4. Suggest an outfit using the user's wardrobe.
5. Generate a short fit card/caption for the selected item.

---

## Core Tools

### 1. `search_listings(description, size=None, max_price=None)`

Searches `data/listings.json` for matching listings.

It supports:

- keyword matching
- synonym expansion
- size filtering
- price filtering
- relevance scoring
- no-results handling

Search is deterministic instead of LLM-based so retrieval stays reliable and testable.

### 2. `suggest_outfit(new_item, wardrobe)`

Suggests 1–2 outfits using the selected listing and the user's wardrobe.

If a Groq API key is available, this tool uses an LLM to create natural styling advice. If Groq is unavailable, it falls back to deterministic styling logic so the app still runs locally.

### 3. `create_fit_card(outfit, new_item)`

Creates a short shareable caption for the thrifted find.

The caption mentions the item, price, platform, and overall outfit vibe.

---

## Agent Flow

```text
User query
   ↓
parse_query()
   ↓
search_listings()
   ↓
select top listing
   ↓
suggest_outfit()
   ↓
create_fit_card()
   ↓
Gradio UI output
```

The agent stores state in a session dictionary:

```python
{
    "query": ...,
    "parsed": ...,
    "search_results": ...,
    "selected_item": ...,
    "wardrobe": ...,
    "outfit_suggestion": ...,
    "fit_card": ...,
    "error": ...,
}
```

This makes the tool chain easy to inspect and debug.

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

The app still works without a Groq key because the styling tools include fallback behavior.

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
- fit card guardrails
- full happy-path agent loop
- full no-results agent loop

Latest local result:

```text
7 passed
```

---

## Error Handling

FitFindr handles several failure cases:

- empty user query
- no matching listings
- missing or empty wardrobe
- missing Groq API key
- empty outfit text before fit-card generation

When no listing matches, the agent stops early and returns a helpful message instead of pretending it found an item.

---

## AI Tool Usage

AI assistance was used to help plan, implement, and debug the project.

The deterministic parts of the agent, such as query parsing and listing search, were kept rule-based so they are reliable and testable. LLM usage is limited to natural-language styling and caption generation, where creative text output is useful.

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
