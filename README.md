# which-llm

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Daily refresh](https://img.shields.io/github/actions/workflow/status/ariobarin/which-llm/refresh.yml?label=daily%20refresh)](https://github.com/ariobarin/which-llm/actions/workflows/refresh.yml)
[![Last refresh](https://img.shields.io/github/last-commit/ariobarin/which-llm?label=last%20refresh)](https://github.com/ariobarin/which-llm/commits/main)
[![GitHub stars](https://img.shields.io/github/stars/ariobarin/which-llm?style=social)](https://github.com/ariobarin/which-llm/stargazers)

> **A Claude Code skill that gives your agent current LLM intelligence, cost, capability, and OpenRouter slug data for 520+ models — refreshed daily.**

LLM lineups churn every few weeks; your agent's training data doesn't. Ask "which model should I use for X" and this skill answers from a current scrape of [Artificial Analysis](https://artificialanalysis.ai/models), cross-referenced with the [OpenRouter](https://openrouter.ai) catalog (including which slugs have a `:free` tier).

```text
$ uv run py query.py recommend --intel-min 50 --max-cost 500 --image --limit 5

slug                    name                                     creator  intel  idx-run$  ctx       free  openrouter
----------------------  ---------------------------------------  -------  -----  --------  --------  ----  ----------------------------
deepseek-v4-pro         DeepSeek V4 Pro (Reasoning, Max Effort)  DeepSeek 51.5   $267.82   1000000   -     deepseek/deepseek-v4-pro
grok-4-3                Grok 4.3 (high)                          xAI      53.2   $395.17   1000000   -     x-ai/grok-4.3
mimo-v2-5-pro           MiMo-V2.5-Pro                            Xiaomi   53.8   $461.59   1000000   -     xiaomi/mimo-v2.5-pro
```

> `idx-run$` is the USD to run AA's full benchmark suite once on the model. It's a relative inference-cost proxy, **not** a per-call price. For actual API pricing, use `price_1m_input_tokens` and `price_1m_output_tokens`.

## Install

### Via Claude Code plugin marketplace (recommended)

```text
/plugin marketplace add ariobarin/which-llm
/plugin install which-llm@which-llm
```

Auto-updates whenever this repo ships a new version.

### Direct (no plugin system)

```bash
git clone https://github.com/ariobarin/which-llm /tmp/which-llm
cp -r /tmp/which-llm/plugins/which-llm/skills/which-llm ~/.claude/skills/which-llm
```

Requirements: Python 3.10+ and [`uv`](https://docs.astral.sh/uv/). The shipped data snapshot is auto-refreshed daily by GitHub Actions — you generally don't need to refresh manually.

## What your agent will do with it

Trigger phrases that activate the skill:

> *"I need a vision model under $500 with reasoning. What are my options?"*
> *"Is there a free version of DeepSeek V4 Flash on OpenRouter?"*
> *"Cheapest model with intelligence > 50?"*
> *"Compare GPT-5.5, Claude Opus 4.7, and Gemini 3.1 Pro."*

Under the hood the agent runs short `query.py` commands and reasons over the output.

## Commands

| Command | Use |
|---|---|
| `query.py status` | Data freshness, model count, OpenRouter enrichment status |
| `query.py refresh` | Re-scrape AA + cross-reference OR (~10s) |
| `query.py find <pattern>` | Substring match on name / slug / creator |
| `query.py info <slug>` | Full per-model info: benchmarks, pricing, OR slugs, modalities |
| `query.py list [--limit N] [--by-cost] [--max-cost N]` | Top N |
| `query.py frontier` | Cost-vs-intelligence Pareto frontier |
| `query.py recommend --intel-min N --max-cost M [...]` | Best fit under constraints |
| `query.py free` | All `:free` OpenRouter models |

All commands accept modality filters: `--text` (default), `--no-text`, `--image`, `--video`, `--audio`, `--free`. They AND together.

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
