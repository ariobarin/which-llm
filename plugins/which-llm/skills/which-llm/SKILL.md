---
name: which-llm
description: Look up current LLM intelligence, cost-to-run, benchmark scores, capabilities, and OpenRouter slugs (including :free tier). Use whenever the user asks "which model should I use", "what's the cheapest model that…", "compare model X vs Y", "is there a free version of X", "what's the OpenRouter slug for X", is about to wire up, swap, or hardcode any LLM (OpenAI/Anthropic/OpenRouter/Gemini/xAI/DeepSeek/Mistral/Qwen/Llama/Kimi) in code, or asks about a specific model's price, context window, modality support, or benchmark scores.
---

# which-llm

Up-to-date data on ~520 LLMs scraped from artificialanalysis.ai and cross-referenced with the OpenRouter catalog. Trained-in model knowledge goes stale fast. Use this skill instead of guessing.

## Commands

Three verbs. Run from this skill's directory.

| Command | Use |
|---|---|
| `uv run python query.py models [<pattern>] [filters]` | Filter / rank / list models. Default: top 20 by intelligence. |
| `uv run python query.py show <slug>` | Full profile for one model. Accepts fuzzy slug when unambiguous. |
| `uv run python query.py data status` | Data freshness + model count. |
| `uv run python query.py data refresh` | Re-scrape AA + re-cross-reference OR (~10s). |

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
| `--creator a,b` | Keep only these creators (CSV substrings, case-insensitive, OR within). `--list-creators` shows available names. |
| `--list-creators` | List every creator and its model count, then exit. |
| `--max-latency N` | Max end-to-end response latency in seconds (drops models AA hasn't speed-tested). |
| `--modality text,image,...` | Required input modalities (CSV). Default `text`. `any` to disable. |
| `--reasoning` / `--no-reasoning` | Filter on reasoning capability. |
| `--open-weights` / `--no-open-weights` | Filter on open-weights status. |
| `--json` | Emit JSON instead of a table. |

## Key fields and their units

- `intelligence_index`: composite 0-100 score across AA's benchmark suite (GPQA, HLE, MMLU-Pro, LiveCodeBench, MATH-500, AIME, SciCode, tau2, HumanEval, ...). **Caveat:** a single composite hides which capabilities drive the score. A model at 51.5 might beat one at 50.8 purely on math benchmarks while being worse at tool-calling. For narrow use cases, check the individual benchmarks via `show <slug>` rather than relying on the composite alone.
- `intelligence_index_cost_usd` (table header `idx-run$`): USD to run AA's full benchmark suite once on this model. **Relative inference-cost proxy, not a per-call price.**
- `price_1m_input_tokens` / `price_1m_output_tokens`: USD per million tokens. **Use these for actual API cost calculations.**
- `openrouter_slug`: paid OR endpoint, e.g. `anthropic/claude-opus-4.7`. Goes straight into the OR API.
- `openrouter_free_slug`: `:free` OR endpoint when available, e.g. `deepseek/deepseek-v4-flash:free`. **Caveat:** `:free` is a rate-limited promotional/community listing (often via Chutes or similar), not a tier of the same model. Different quantization, daily caps, no SLA. Recommend for prototyping only — flag this to the user when surfacing it.
- `context_window_tokens`: usable context length.
- `ttft_seconds` / `e2e_response_seconds`: AA's measured time-to-first-answer-token and full end-to-end response latency, in seconds, on a standardized run. **Lower = faster.** **Caveats:** for reasoning models both include thinking time, so they read slower; the value is one fixed-length run, not a per-call guarantee; `null`/`-` means AA hasn't speed-tested that model (not "instant"). For throughput-bound agent loops, `e2e_response_seconds` is the headline; for streaming UIs, `ttft_seconds` matters more.
- `reasoning_model` (bool): whether the model has an explicit reasoning / thinking mode.
- `input_modality_text` / `image` / `video` / `speech`: capability flags.

- `creator_name` / `creator_slug`: the lab that made the model. AA carries **no country/region field**, so filter geography by naming the labs (`--creator`), not by country.

The full enriched dataset lives in `artifacts/models_enriched.csv` (60+ columns) and `artifacts/models.json` (every original AA field). Read directly if `query.py` lacks a needed filter.

## Examples

```text
# Strongest model under $200 with image input:
uv run python query.py models --intel-min 0 --max-cost 200 --modality text,image --top 5

# All free OpenRouter models, cheapest first:
uv run python query.py models --free --sort cost --top 0

# Cheapest model with intelligence above 50 that supports reasoning:
uv run python query.py models --intel-min 50 --reasoning --sort cost --top 5

# Fastest non-reasoning models, by measured end-to-end latency:
uv run python query.py models --no-reasoning --sort speed --top 10

# Capable models that respond in under 6s end-to-end:
uv run python query.py models --no-reasoning --intel-min 30 --max-latency 6 --sort intel

# Discover creator names, then filter to specific labs:
uv run python query.py models --list-creators
uv run python query.py models --creator deepseek,alibaba --no-reasoning --sort speed

# Fast non-reasoning models from Chinese labs (AA has no country field, so name
# the creators explicitly; --list-creators shows the current roster):
uv run python query.py models --no-reasoning --sort speed \
  --creator alibaba,deepseek,moonshot,zhipu,z-ai,minimax,tencent,stepfun,baidu,xiaomi,01-ai,inclusion,bytedance

# Pareto frontier under $750:
uv run python query.py models --pareto --max-cost 750

# Look up a specific model:
uv run python query.py show claude-opus-4-7

# Compare GPT-5 variants (substring match):
uv run python query.py models gpt-5 --top 10
```

## Presenting results

Report the data, let the user choose. The tool surfaces tradeoffs; it does not pick winners.

- **Show both cost columns whenever cost is in play.** Per-token price (`price_1m_input_tokens` / `price_1m_output_tokens`) is the real API bill; `idx-run$` (`intelligence_index_cost_usd`) captures how many tokens a model spends to do the same work (verbosity). They can disagree sharply — a model with a low per-token price can still have a high `idx-run$`. Dropping either hides a real axis, so include both rather than collapsing to one.
- **Stay neutral.** Present intelligence, cost, speed, context, and modality side by side and let the numbers stand. Do not editorialize toward a single "best" or "default" pick, rank by a hidden weighting, or omit a column because it complicates the story. If the user asked to optimize one axis, sort by it and say so plainly; otherwise show the spread.
- **Attach the caveat, not a verdict.** When a number has a footnote (`idx-run$` is a relative proxy not a per-call price; latency is one fixed run and includes reasoning time for thinking models; `:free` is a rate-limited promo listing; the composite `intelligence_index` hides per-benchmark detail), state it neutrally next to the figure instead of using it to argue for or against a model.
- **Make a recommendation only when asked**, and when you do, show the comparison table first and label it as your read of their stated priorities, not a property of the data.

## When NOT to use

- Benchmarks AA doesn't track (domain evals, custom evals). Use the model's own published numbers.
- Models < 1 week old that AA hasn't indexed yet.
- When you need an authoritative per-API-call price for a non-OR-hosted provider — verify directly with that provider.

## Refresh policy

Data is auto-refreshed daily by a GitHub Action; the snapshot shipped with the skill is rarely > 24h stale. Run `uv run python query.py data status` to check, and `data refresh` if needed. A manual refresh takes ~10s.

## Visual exploration (optional)

`plot_pareto.py` renders an Intelligence-vs-X Pareto chart to `artifacts/pareto.png`. `--axis cost` (default) plots intelligence vs idx-run$; `--axis speed` plots intelligence vs measured end-to-end latency (the "smart and fast" frontier). Supports the same modality / `--free-only` flags plus `--reasoning/--no-reasoning` and `--creator a,b`. Useful when the user wants a visual; otherwise the CLI output is more agent-friendly.

```text
uv run python plot_pareto.py --max-cost 750 --near 15
uv run python plot_pareto.py --free-only --max-cost 100000

# Smart-and-fast frontier for non-reasoning models:
uv run python plot_pareto.py --axis speed --no-reasoning --max-latency 30

# Same, scoped to specific labs:
uv run python plot_pareto.py --axis speed --no-reasoning --creator alibaba,deepseek
```
