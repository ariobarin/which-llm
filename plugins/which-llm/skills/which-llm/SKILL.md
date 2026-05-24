---
name: which-llm
description: Look up current LLM intelligence, cost-to-run, benchmark scores, capabilities, and OpenRouter slugs (including :free tier). Use whenever the user asks "which model should I use", "what's the cheapest model that…", "compare model X vs Y", "is there a free version of X", "what's the OpenRouter slug for X", is about to wire up, swap, or hardcode any LLM (OpenAI/Anthropic/OpenRouter/Gemini/xAI/DeepSeek/Mistral/Qwen/Llama/Kimi) in code, or asks about a specific model's price, context window, modality support, or benchmark scores.
---

# which-llm

Up-to-date data on ~520 LLMs scraped from artificialanalysis.ai and cross-referenced with the OpenRouter catalog. Trains-time knowledge of model lineups goes stale fast. Use this skill instead of guessing.

## When to invoke

Trigger on any of:

- "Which model should I use for X?" / "What's the cheapest model with intelligence > N?"
- "Is there a free version of model X?" / "What's the OpenRouter slug for X?"
- "Compare model A vs B" / "Find me a vision model under $Y"
- Picking a model when writing or modifying code that calls an LLM API
- Recommending a model the user could swap in for cost or capability reasons

## Commands

Run from this skill's directory. Always use `uv run python query.py <cmd>`.

| Command | What it does |
|---|---|
| `status` | Show data freshness, model count, whether OR enrichment ran. |
| `refresh` | Re-scrape AA + re-cross-reference OR. Run if `status` reports age > 7 days. |
| `find <pattern>` | Substring match on name / slug / creator. Returns matches sorted by intelligence. |
| `info <slug>` | Full info for one model: benchmarks, pricing, OR slugs, modalities. Accepts fuzzy slug if unambiguous. |
| `list [--limit N] [--by-cost] [--max-cost N]` | Top N models, default sorted by intelligence. |
| `frontier [--max-cost N] [--min-cost N]` | Intelligence-vs-cost Pareto frontier. |
| `recommend --intel-min N --max-cost M [--reasoning true] [--open-weights] [--context-min N]` | Best fit under constraints. |
| `free` | All OR-free models, sorted by intelligence. |

### Modality filters (all commands)

- `--text` (default ON) / `--no-text`
- `--image`, `--video`, `--audio` (opt-in; AND'd with text)
- `--free` (only models with `:free` OpenRouter variant)

## Key fields and their units

- `intelligence_index`: composite 0-100 score across AA's benchmark suite (GPQA, HLE, MMLU-Pro, LiveCodeBench, MATH-500, AIME, SciCode, tau2, HumanEval, ...).
- `intelligence_index_cost_usd`: USD to run AA's full benchmark suite on this model. Use this as a **relative** inference-cost signal — it's not a per-API-call price.
- `price_1m_input_tokens` / `price_1m_output_tokens`: USD per million tokens. **Use these for actual API cost calculations.**
- `openrouter_slug`: paid OR endpoint, e.g. `anthropic/claude-opus-4.7`. Goes straight into the OR API.
- `openrouter_free_slug`: `:free` OR endpoint when available, e.g. `deepseek/deepseek-v4-flash:free`. **Caveat:** `:free` is a rate-limited promotional/community listing (often via Chutes or similar), not a tier of the same model. Different quantization, daily caps, no SLA. Recommend for prototyping only — flag this to the user when surfacing it.
- `context_window_tokens`: usable context length.
- `reasoning_model` (bool): whether the model has an explicit reasoning / thinking mode.
- `input_modality_text` / `image` / `video` / `speech`: capability flags.

The full enriched dataset lives in `artifacts/models_enriched.csv` (60+ columns) and `artifacts/models.json` (every original AA field). Read directly if `query.py` lacks a needed filter.

## Examples

```text
# What's the strongest model under $200 with image input?
uv run python query.py recommend --intel-min 0 --max-cost 200 --image --limit 5

# Show the free-tier landscape:
uv run python query.py free

# Look up a specific model:
uv run python query.py info claude-opus-4-7

# Cheapest model with intelligence above 50 that supports reasoning:
uv run python query.py recommend --intel-min 50 --reasoning true

# Compare options around the GPT-5 family:
uv run python query.py find gpt-5
```

## When NOT to use

- Benchmarks AA doesn't track (domain evals, custom evals). Use the model's own published numbers.
- Models < 1 week old that AA hasn't indexed yet.
- When you need an authoritative per-API-call price for a non-OR-hosted provider — verify directly with that provider.

## Refresh policy

Run `uv run python query.py refresh` if `status` reports age > 7 days, or before any pricing-sensitive recommendation. A refresh takes ~10 seconds (single HTTP GET to AA + one to OR + parse).

## Visual exploration (optional)

`plot_pareto.py` renders the Intelligence-vs-Cost Pareto chart to `artifacts/pareto.png`. Same modality / free / cost flags as `query.py`. Useful when the user wants a visual, otherwise the CLI output is more agent-friendly.

```text
uv run python plot_pareto.py --max-cost 750 --near 15
uv run python plot_pareto.py --free-only --max-cost 100000
```
