# which-llm

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Daily refresh](https://img.shields.io/github/actions/workflow/status/ariobarin/which-llm/refresh.yml?label=daily%20refresh)](https://github.com/ariobarin/which-llm/actions/workflows/refresh.yml)
[![Last refresh](https://img.shields.io/github/last-commit/ariobarin/which-llm?label=last%20refresh)](https://github.com/ariobarin/which-llm/commits/main)
[![GitHub stars](https://img.shields.io/github/stars/ariobarin/which-llm?style=flat&logo=github)](https://github.com/ariobarin/which-llm/stargazers)

A Claude Code skill that resolves "which model should I use?" to a real, current answer. Joins the [Artificial Analysis](https://artificialanalysis.ai/models) leaderboard (520+ models, intelligence/cost/benchmarks) with the [OpenRouter](https://openrouter.ai) catalog (slug availability, `:free` tier reality) into a single queryable dataset your agent can reason over. Refreshed daily.

## Install

```text
/plugin marketplace add ariobarin/which-llm
/plugin install which-llm@which-llm
```

Auto-updates when this repo ships a new version. Requires Python 3.10+ and [`uv`](https://docs.astral.sh/uv/).

<details>
<summary>Direct install without the plugin system</summary>

```bash
git clone https://github.com/ariobarin/which-llm /tmp/which-llm
cp -r /tmp/which-llm/plugins/which-llm/skills/which-llm ~/.claude/skills/which-llm
```
</details>

## Example output

```text
$ uv run python query.py models --intel-min 50 --max-cost 500 --modality text,image --top 5

slug                  name                                     creator   intel  idx-run$  ctx      free  openrouter
--------------------  ---------------------------------------  --------  -----  --------  -------  ----  --------------------------
deepseek-v4-pro       DeepSeek V4 Pro (Reasoning, Max Effort)  DeepSeek  51.5   $267.82   1000000        deepseek/deepseek-v4-pro
grok-4-3              Grok 4.3 (high)                          xAI       53.2   $395.17   1000000        x-ai/grok-4.3
mimo-v2-5-pro         MiMo-V2.5-Pro                            Xiaomi    53.8   $461.59   1000000        xiaomi/mimo-v2.5-pro
```

**`idx-run$` is the headline metric.** It's the USD it took Artificial Analysis to run their full Intelligence Index benchmark suite once on that model. Because it captures *how many tokens a model burns to reach its score* — a verbose reasoning model costs more even at the same per-token price — it's the truest "intelligence per dollar" signal. Sort by it to find models that are both smart *and* cost-efficient. It is **not** a per-call price you pay; for that, use `price_1m_input_tokens` / `price_1m_output_tokens`.

> ⚠ **About `:free` OpenRouter slugs:** These aren't "the free version of the model" — they're community / promotional endpoints (often via Chutes or similar) with aggressive rate limits, daily caps, and sometimes different quantization than the paid listing. Great for prototyping; don't wire them into production without testing throughput against your real load.

## What your agent will do with it

Trigger phrases that activate the skill:

> *"I need a vision model under $500 with reasoning. What are my options?"*
> *"Is there a free version of DeepSeek V4 Flash on OpenRouter?"*
> *"Cheapest model with intelligence > 50?"*
> *"Compare GPT-5.5, Claude Opus 4.7, and Gemini 3.1 Pro."*

Under the hood the agent runs short `query.py` commands and reasons over the output.

## Commands

Three verbs, one consistent table schema.

| Command | Use |
|---|---|
| `query.py models [<pattern>] [filters]` | Filter / rank / list models. Default: top 20 by intel. |
| `query.py show <slug>` | Full per-model profile (benchmarks, pricing, OR slugs, modalities). Accepts fuzzy slug if unambiguous. |
| `query.py data status` | Data freshness, model count, OpenRouter enrichment status |
| `query.py data refresh` | Re-scrape AA + cross-reference OR (~10s) |

`models` flags: `--top N`, `--sort intel|cost|ctx`, `--pareto`, `--free`, `--intel-min N`, `--max-cost N`, `--min-cost N`, `--context-min N`, `--modality text,image,audio,video`, `--reasoning`/`--no-reasoning`, `--open-weights`/`--no-open-weights`, `--json`.

`plot_pareto.py` renders the Intelligence-vs-Cost Pareto chart as a PNG for visual exploration.

## How it works

The dataset is built from three layers, merged by `build.py`:

1. **`scrape.py`** — fetches `artificialanalysis.ai/models` (an 8 MB HTML page) and parses the Next.js RSC payload, extracting every model with its full schema (60+ fields). This is the **primary** source and the *only* one that carries `idx-run$`, context window, modality flags, and open-weights status.
2. **`fetch_api.py`** — pulls Artificial Analysis's official [free API](https://artificialanalysis.ai/api-reference) (authoritative benchmarks/pricing keyed by stable IDs). Used to **cross-check** the scrape and as a **graceful fallback**: if AA changes their page and the parser breaks, the build degrades to API data instead of shipping nothing.
3. **`enrich.py`** — matches each model against the OpenRouter catalog for slugs, `:free` availability, and a context/modality cross-check. Current match rate ~51% — the rest are mostly models OpenRouter doesn't carry.

`query.py` reads the merged CSV. A daily GitHub Action rebuilds and commits any changes, so the shipped snapshot is rarely more than 24h stale.

**Data source modes** (`WHICH_LLM_SOURCE` env var):

| Mode | Behavior |
|---|---|
| `merged` *(default)* | Scrape primary; degrade to the API base if the parser breaks. |
| `scrape` | Scrape only; fail hard if the parser breaks. |
| `api` | Official API only — never scrapes. Sanctioned-source-only, for users who prefer not to scrape AA. Loses `idx-run$`, context, modality, open-weights. |

The scrape needs no credentials. The API layer uses a free key — set `AA_API_KEY` (env or a `.env` file at the repo root); get one at [artificialanalysis.ai](https://artificialanalysis.ai/). Without a key, `merged` mode still ships the scrape.

## Data files

| File | Contents |
|---|---|
| `artifacts/models_enriched.csv` | The full merged dataset (60+ columns per row) |
| `artifacts/models.json` | Original AA scrape fields, preserved exactly |
| `artifacts/models_api.json` | Raw Artificial Analysis API response |
| `artifacts/openrouter.json` | Raw OpenRouter catalog |

## When NOT to use

- Benchmarks AA doesn't track (domain-specific evals).
- Models too new for AA to have indexed (<1 week post-release sometimes).
- For an authoritative per-API-call price on a non-OR provider — verify directly with that provider.

## Data, attribution & usage

Benchmark, intelligence, and pricing data is **from [Artificial Analysis](https://artificialanalysis.ai)**; model availability and slugs are **from [OpenRouter](https://openrouter.ai)**. This project is an independent tool that surfaces and points back to their data to help people choose models — it is not affiliated with or endorsed by either.

- **Attribution:** any output derived from this dataset should credit Artificial Analysis (https://artificialanalysis.ai). The skill emits this automatically.
- **Code** in this repo is MIT (see [`LICENSE`](LICENSE)). The **underlying data remains the property of its sources** and is subject to their terms — see Artificial Analysis's [Terms of Use](https://artificialanalysis.ai/docs/legal/Terms-of-Use.pdf). The MIT license covers the code, not the data.
- **If you're a rightsholder** at Artificial Analysis or OpenRouter and would like a change to how this tool sources or presents your data, please [open an issue](https://github.com/ariobarin/which-llm/issues) or email the maintainer — we'll respond and comply promptly.

## License

Code: MIT. See [`LICENSE`](LICENSE).
