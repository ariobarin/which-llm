---
name: which-llm
description: Look up current LLM intelligence, cost-to-run, benchmark scores, capabilities, and OpenRouter slugs (including :free tier). Use whenever the user asks "which model should I use", "what's the cheapest model that...", "compare model X vs Y", "is there a free version of X", "what's the OpenRouter slug for X", is about to wire up, swap, or hardcode any LLM (OpenAI/Anthropic/OpenRouter/Gemini/xAI/DeepSeek/Mistral/Qwen/Llama/Kimi) in code, or asks about a specific model's price, context window, modality support, or benchmark scores.
---

# which-llm

Up-to-date data on ~520 LLMs scraped from artificialanalysis.ai and cross-referenced with the OpenRouter catalog. Trained-in model knowledge goes stale fast. Use this skill instead of guessing.

## Agent workflow

1. Run commands from this skill directory. Use plain `python`. Do not assume `uv` is installed.
2. Start with `python query.py data status` when freshness matters.
3. Use `python query.py models ...` for shortlists and `python query.py show <slug>` before recommending one model.
4. In the answer, separate `idx-run$` from real API pricing. `idx-run$` is a benchmark-run cost proxy. `in$/1m` and `out$/1m` are the per-token API prices.
5. If the user asks for an OpenRouter model, prefer `openrouter_slug` for production. Mention `openrouter_free_slug` only as a prototype option because `:free` endpoints have rate limits and can differ from the paid listing.

## Commands

Three verbs. Run from this skill's directory.

| Command | Use |
|---|---|
| `python query.py models [<pattern>] [filters]` | Filter, rank, or list models. Default: top 20 by intelligence. |
| `python query.py show <slug>` | Full profile for one model. Accepts fuzzy slug when unambiguous. |
| `python query.py data status` | Data freshness and model count. |
| `python query.py data refresh` | Re-scrape AA and re-cross-reference OR. |

### `models` flags

| Flag | Meaning |
|---|---|
| `--top N` | Max rows (default 20; `0` = unlimited). |
| `--sort intel\|cost\|ctx\|speed` | Primary sort key (default: intel descending). `speed` = end-to-end latency ascending. |
| `--pareto` | Filter to cost-vs-intel Pareto frontier; ignores `--sort`. |
| `--free` | Only models with a `:free` OpenRouter variant. |
| `--intel-min N` | Minimum intelligence_index. |
| `--max-cost N` / `--min-cost N` | Idx-run$ bounds (USD). |
| `--context-min N` | Minimum context window in tokens. |
| `--max-latency N` | Max end-to-end response latency in seconds (drops models AA has not speed-tested). |
| `--modality text,image,...` | Required input modalities (CSV). Default `text`. `any` to disable. |
| `--reasoning` / `--no-reasoning` | Filter on reasoning capability. |
| `--open-weights` / `--no-open-weights` | Filter on open-weights status. |
| `--json` | Emit JSON instead of a table. |

## Common recipes

| User intent | Command |
|---|---|
| Cheapest strong reasoning models | `python query.py models --intel-min 50 --reasoning --sort cost --top 8` |
| Strong vision models under a budget | `python query.py models --modality text,image --max-cost 500 --sort intel --top 8` |
| Fast agent-loop candidates | `python query.py models --no-reasoning --max-latency 6 --sort intel --top 8` |
| Cheap long-context models | `python query.py models --context-min 256000 --sort cost --top 8` |
| Open-weights options | `python query.py models --open-weights --sort intel --top 8` |
| OpenRouter free prototypes | `python query.py models --free --sort cost --top 20` |
| Compare one family or provider | `python query.py models <pattern> --top 10` |
| Inspect before final recommendation | `python query.py show <slug>` |

## Key fields and their units

- `intelligence_index`: composite 0-100 score across AA's benchmark suite (GPQA, HLE, MMLU-Pro, LiveCodeBench, MATH-500, AIME, SciCode, tau2, HumanEval, ...). **Caveat:** a single composite hides which capabilities drive the score. A model at 51.5 might beat one at 50.8 purely on math benchmarks while being worse at tool-calling. For narrow use cases, check the individual benchmarks via `show <slug>` rather than relying on the composite alone.
- Cost priority for comparisons: `idx-run$` vs intelligence first, then token-use / latency vs intelligence, then agentic, then coding, then blended token price.
- `intelligence_index_cost_usd` (table header `idx-run$`): USD to run AA's full benchmark suite once on this model. Best available inference-cost proxy because it reflects both token price and tokens burned.
- `price_1m_input_tokens` / `price_1m_output_tokens` (table headers `in$/1m` / `out$/1m`): USD per million tokens. Use only when estimating a known token budget.
- `openrouter_slug`: paid OR endpoint, e.g. `anthropic/claude-opus-4.7`. Goes straight into the OR API.
- `openrouter_free_slug`: `:free` OR endpoint when available, e.g. `deepseek/deepseek-v4-flash:free`. `:free` is a rate-limited promotional/community listing, not a tier of the same model. Different quantization, daily caps, and no SLA are common. Recommend for prototyping only.
- `context_window_tokens`: usable context length.
- `ttft_seconds` / `e2e_response_seconds`: AA's measured time-to-first-answer-token and full end-to-end response latency, in seconds, on a standardized run. Lower is faster. For reasoning models both include thinking time. `null` or `-` means AA has not speed-tested that model.
- `reasoning_model` (bool): whether the model has an explicit reasoning or thinking mode.
- `input_modality_text` / `image` / `video` / `speech`: capability flags.

The full enriched dataset lives in `artifacts/models_enriched.csv` (60+ columns) and `artifacts/models.json` (every original AA field). Read directly if `query.py` lacks a needed filter.

## Examples

```text
# Strongest model under $200 with image input:
python query.py models --intel-min 0 --max-cost 200 --modality text,image --top 5

# All free OpenRouter models, cheapest first:
python query.py models --free --sort cost --top 0

# Cheapest model with intelligence above 50 that supports reasoning:
python query.py models --intel-min 50 --reasoning --sort cost --top 5

# Fastest non-reasoning models, by measured end-to-end latency:
python query.py models --no-reasoning --sort speed --top 10

# Capable models that respond in under 6s end-to-end:
python query.py models --no-reasoning --intel-min 30 --max-latency 6 --sort intel

# Pareto frontier under $750:
python query.py models --pareto --max-cost 750

# Look up a specific model:
python query.py show claude-opus-4-7

# Compare GPT-5 variants (substring match):
python query.py models gpt-5 --top 10
```

## When NOT to use

- Benchmarks AA does not track (domain evals, custom evals). Use the model's own published numbers.
- Models less than 1 week old that AA has not indexed yet.
- When you need an authoritative per-API-call price for a non-OR-hosted provider. Verify directly with that provider.

## Refresh policy

Data is auto-refreshed daily by a GitHub Action; the snapshot shipped with the skill is rarely more than 24h stale. Run `python query.py data status` to check, and `python query.py data refresh` if needed. A manual refresh usually takes a few seconds.

## Visual exploration (optional)

`plot_pareto.py` renders the Intelligence-vs-Cost Pareto chart to `artifacts/pareto.png`. Same modality, free, and cost flags. Useful when the user wants a visual; otherwise the CLI output is more agent-friendly. Plotting needs optional `matplotlib` and `adjustText` packages.

```text
python plot_pareto.py --max-cost 750 --near 15
python plot_pareto.py --free-only --max-cost 100000
python plot_pareto.py --creator OpenAI --creator Anthropic --x-field e2e_response_seconds --y-field intelligence_index --max-cost 300
python plot_pareto.py --creator OpenAI --creator Anthropic --x-field price_1m_input_tokens --y-field agentic_index --max-cost 100
python plot_pareto.py --creator OpenAI --creator Anthropic --x-field price_1m_output_tokens --y-field coding_index --max-cost 100
python plot_pareto.py --creator OpenAI --creator Anthropic --x-field price_1m_blended_7_2_1 --y-field intelligence_index --max-cost 100
```
