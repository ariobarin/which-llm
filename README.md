# which-llm

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Daily refresh](https://img.shields.io/github/actions/workflow/status/ariobarin/which-llm/refresh.yml?label=daily%20refresh)](https://github.com/ariobarin/which-llm/actions/workflows/refresh.yml)
[![Last refresh](https://img.shields.io/github/last-commit/ariobarin/which-llm?label=last%20refresh)](https://github.com/ariobarin/which-llm/commits/main)
[![GitHub stars](https://img.shields.io/github/stars/ariobarin/which-llm?style=flat&logo=github)](https://github.com/ariobarin/which-llm/stargazers)

LLM lineups churn every few weeks; your agent's training data doesn't. Ask "which model should I use for X" and this skill answers from a current scrape of [Artificial Analysis](https://artificialanalysis.ai/models), cross-referenced with the [OpenRouter](https://openrouter.ai) catalog (including which slugs have a `:free` tier). 520+ models, refreshed daily.

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

`idx-run$` = USD to run AA's full benchmark suite once on the model — a relative inference-cost proxy, *not* a per-call price. For actual API pricing, use `price_1m_input_tokens` / `price_1m_output_tokens`.

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

1. `scrape.py` fetches `artificialanalysis.ai/models` (an 8 MB HTML page) and parses the Next.js RSC payload, extracting every model object with its full schema — 60+ fields including individual benchmarks, pricing tiers, modality flags, context window, reasoning capability.
2. `enrich.py` fetches the OpenRouter catalog and matches each AA model against it by name, with token-multiset fallback for word-order differences. Current match rate ~51% — the rest are mostly models OpenRouter doesn't carry.
3. `query.py` reads the merged CSV and answers structured questions.
4. A daily GitHub Action re-runs steps 1-2 and commits any changes, so the shipped snapshot is rarely more than 24h stale.

No API keys, no auth, no rate-limited services — just public pages.

## Data files

| File | Contents |
|---|---|
| `artifacts/models_enriched.csv` | The full merged dataset (60+ columns per row) |
| `artifacts/models.json` | Original AA fields, preserved exactly |
| `artifacts/openrouter.json` | Raw OpenRouter catalog |

## When NOT to use

- Benchmarks AA doesn't track (domain-specific evals).
- Models too new for AA to have indexed (<1 week post-release sometimes).
- For an authoritative per-API-call price on a non-OR provider — verify directly with that provider.

## License

MIT. See [`LICENSE`](LICENSE).

## Credits

Data from [Artificial Analysis](https://artificialanalysis.ai) and [OpenRouter](https://openrouter.ai). Scrapes only public pages, no credentials required.
