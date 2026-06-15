# which-llm

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Daily refresh](https://img.shields.io/github/actions/workflow/status/ariobarin/which-llm/refresh.yml?label=daily%20refresh)](https://github.com/ariobarin/which-llm/actions/workflows/refresh.yml)
[![Last refresh](https://img.shields.io/github/last-commit/ariobarin/which-llm?label=last%20refresh)](https://github.com/ariobarin/which-llm/commits/main)
[![GitHub stars](https://img.shields.io/github/stars/ariobarin/which-llm?style=flat&logo=github)](https://github.com/ariobarin/which-llm/stargazers)

An agent skill that resolves "which model should I use?" to a real, current answer. It joins the [Artificial Analysis](https://artificialanalysis.ai/models) leaderboard (520+ models, intelligence, cost, benchmarks) with the [OpenRouter](https://openrouter.ai) catalog (slug availability, `:free` tier reality) into a single queryable dataset your agent can reason over. Checked for refresh daily.

## Install

```text
/plugin marketplace add ariobarin/which-llm
/plugin install which-llm@which-llm
```

Auto-updates when this repo ships a new version. Requires Python 3.10+. Cached queries and data refresh use the Python standard library.

<details>
<summary>Direct install without the plugin system</summary>

```bash
git clone https://github.com/ariobarin/which-llm /tmp/which-llm
cp -r /tmp/which-llm/plugins/which-llm/skills/which-llm ~/.claude/skills/which-llm
```
</details>

## Example output

Example values are from one checked-in snapshot and will move as data refreshes.

```text
$ python query.py models --intel-min 50 --reasoning --sort tokens --top 3

slug                    name                    creator  intel  idx-run$  idx-tok  in$/1m  out$/1m  ctx      e2e_s  free  openrouter
----------------------  ----------------------  -------  -----  --------  -------  ------  -------  -------  -----  ----  -----------------------------
gpt-5-5-low             GPT-5.5 (low)           OpenAI   50.8   $500.67   65.1M    $5.00   $30.00   922000   12.1         openai/gpt-5.5
gpt-5-5-medium          GPT-5.5 (medium)        OpenAI   56.7   $1,199    127.5M   $5.00   $30.00   922000   18.7         openai/gpt-5.5
gemini-3-1-pro-preview  Gemini 3.1 Pro Preview  Google   57.2   $892.28   159.7M   $2.00   $12.00   1000000  26.3         google/gemini-3.1-pro-preview
```

`idx-run$` is USD to run AA's full benchmark suite once on the model. `idx-tok` is total tokens consumed by that benchmark run. Both are relative benchmark-run proxies, not per-call prices. For actual API pricing, use `in$/1m` and `out$/1m` in the table, or the `price_1m_input_tokens` / `price_1m_output_tokens` fields.

**About `:free` OpenRouter slugs:** These are not "the free version of the model". They are community / promotional endpoints (often via Chutes or similar) with aggressive rate limits, daily caps, and sometimes different quantization than the paid listing. They are useful for prototyping. Do not wire them into production without testing throughput against your real load.

## What your agent will do with it

Trigger phrases that activate the skill:

> *"I need a vision model under $500 with reasoning. What are my options?"*
> *"Is there a free version of DeepSeek V4 Flash on OpenRouter?"*
> *"Cheapest model with intelligence > 50?"*
> *"Compare GPT-5.5, Claude Opus 4.7, and Gemini 3.1 Pro."*

Under the hood the agent runs short `python query.py` commands and reasons over the output.

Agent recipe examples:

```text
python query.py data status
python query.py models --intel-min 50 --reasoning --sort cost --top 8
python query.py models --intel-min 50 --sort tokens --top 8
python query.py models --modality text,image --max-cost 500 --sort intel --top 8
python query.py models --free --sort cost --top 20
python query.py compare claude-opus-4-7 gpt-5
python query.py slug claude-opus-4-7
python query.py show claude-opus-4-7
```

## Commands

Short intent commands for agents.

| Command | Use |
|---|---|
| `query.py models [<pattern>] [filters]` | Filter, rank, or list models. Default: top 20 by intel. |
| `query.py compare <model>...` | Compare exact or fuzzy model names in one table. |
| `query.py slug <model>` | Return paid and free OpenRouter slugs for one model. |
| `query.py show <slug>` | Full per-model profile (benchmarks, pricing, OR slugs, modalities). Accepts fuzzy slug if unambiguous. |
| `query.py data status` | Data freshness, model count, OpenRouter enrichment status |
| `query.py data refresh` | Re-scrape AA and cross-reference OR |

`models` flags: `--top N`, `--sort intel|cost|ctx|speed|tokens`, `--pareto`, `--free`, `--intel-min N`, `--max-cost N`, `--min-cost N`, `--max-index-tokens N`, `--min-index-tokens N`, `--context-min N`, `--max-latency N`, `--modality text,image,audio,video`, `--reasoning`/`--no-reasoning`, `--open-weights`/`--no-open-weights`, `--json`.

Compatibility aliases are available for agents that try older verbs: `find`, `list`, `recommend`, `frontier`, `free`, `info`, `status`, and `refresh`.

`plot_pareto.py` renders the Intelligence-vs-Cost Pareto chart as a PNG for visual exploration. It needs optional `matplotlib` and `adjustText` packages.

## How it works

1. `scrape.py` fetches `artificialanalysis.ai/models` (an 8 MB HTML page) and parses the Next.js RSC payload, extracting every model object with its full schema: 60+ fields including individual benchmarks, benchmark-run token usage, pricing tiers, modality flags, context window, and reasoning capability.
2. `enrich.py` fetches the OpenRouter catalog and matches each AA model against it by name, with token-multiset fallback for word-order differences. The match rate changes as the AA and OpenRouter catalogs move; unmatched rows are written to `artifacts/unmatched.txt`.
3. `query.py` reads the merged CSV and answers structured questions.
4. A daily GitHub Action re-runs steps 1-2 and commits artifact changes when the fetched data differs. Run `python query.py data status` to see the age of the checked-in snapshot in your checkout.

No API keys, no auth, no rate-limited services. Just public pages.

## Data files

| File | Contents |
|---|---|
| `artifacts/models_enriched.csv` | The full merged dataset (60+ columns per row) |
| `artifacts/models.json` | Original AA fields, preserved exactly |
| `artifacts/openrouter.json` | Raw OpenRouter catalog |

## When NOT to use

- Benchmarks AA does not track (domain-specific evals).
- Models too new for AA to have indexed (less than 1 week post-release sometimes).
- For an authoritative per-API-call price on a non-OR provider, verify directly with that provider.

## License

MIT. See [`LICENSE`](LICENSE).

## Credits

Data from [Artificial Analysis](https://artificialanalysis.ai) and [OpenRouter](https://openrouter.ai). Scrapes only public pages, no credentials required.
