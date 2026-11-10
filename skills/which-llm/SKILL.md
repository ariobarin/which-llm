---
name: which-llm
description: Look up current LLM quality, price, speed, context, modality, benchmark scores, and OpenRouter slugs (including free tier). Use for model recommendations, comparisons, pricing checks, and code changes that add or swap an LLM.
---

# which-llm

A daily Artificial Analysis (AA) plus OpenRouter snapshot with Python commands
to query it. Run the scripts from this skill directory with Python 3.10+; they
need only the standard library. Every command takes `--help`, which lists all
filters and options.

No data ships with the skill. The published daily snapshot is fetched on first
use and again when the local copy is older than two days. If that fetch fails,
the command stops with an error instead of answering from stale data.

## Commands

| Need | Command |
|---|---|
| Ranked models under constraints | `python pick.py [preset] [filters] --sort KEY --top N` |
| Side-by-side comparison | `python compare.py <model>...` |
| Everything about one model | `python profile.py <model>` |
| Natural name to slug, with alternates | `python resolve.py <name>...` |
| OpenRouter paid and free slugs | `python slug.py <model>` |
| Pareto chart (PNG) plus CSV | `python frontier.py [preset] [filters]` |
| Filtered rows as CSV or JSON | `python export.py [preset] [filters] --fields GROUPS` |
| Raw AA datasets as JSON | `python data.py [dataset] [options]` |

- `pick.py` and `export.py` presets: `best`, `vision`, `long-context` (at
  least 256K), `open-weights`, `free`. Sort keys: `intel`, `cost`, `ctx`,
  `tokens`, `speed`, `input-price`, `output-price`.
- `frontier.py` presets: `cost-intel`, `speed-intel`, `tokens-intel`,
  `context-intel`, `input-price-intel`, `output-price-intel`. It needs
  matplotlib.
- Model arguments accept names, AA slugs, or OpenRouter slugs. `compare.py`
  fails on ambiguous names; run `resolve.py` first or pass `--resolve auto`.
- When no rows match, `pick.py` shows labeled one-filter relaxations. Pass
  `--if-empty error` to fail instead.

```text
python pick.py vision --min-intel 40 --sort input-price --top 5
python pick.py long-context --max-input-price 1 --sort cost --top 5
python export.py open-weights --fields pricing,context --format csv
python frontier.py cost-intel --creator OpenAI --creator Anthropic
```

## Reading the numbers

- `in$/1m` and `out$/1m` are API prices per million tokens. They are rates,
  not workload cost, which also depends on token volume, caching, and retries.
- `intel-task$` is AA's measured cost per Intelligence Index task and is what
  `--sort cost` uses. `idx-run$` is the cost of the whole benchmark run and
  `idx-tok` its token use. Neither is a per-call price.
- `--max-run-cost` filters on `idx-run$`. Use `--max-input-price` or
  `--max-output-price` for API prices.
- `openrouter_free_slug` endpoints are for prototyping and can be rate limited.
- `openrouter_data_status` is `live`, `cached` (last known mapping because
  OpenRouter was unreachable; do not present it as current), or `unavailable`.

## Detailed datasets

`python data.py` lists the datasets with row counts, source dates, and
freshness. `python data.py <dataset>` prints ten records; narrow with
`--model TEXT`, `--fields a,b`, `--sort FIELD`, `--ascending`, and `--top N`
(0 means all). Field names and units are AA's, and nested paths work. Print
one record to discover the fields before choosing a sort.

- `catalog`: every model field, including effort levels, licenses, speed
  distributions, and token breakdowns.
- `evaluations`: benchmark subscores, confidence intervals, and domain
  breakdowns.
- `capabilities`: domain indices with their matching task cost, time, and
  tokens.
- `coding-agents`: agent plus model configurations with scores, cost, and
  wall time. An agent configuration's score is not a model-only score.
- `providers`: one row per AA-tracked API endpoint with pricing, performance,
  and features.
- `media/*` and `speech/*`: image, video, and speech leaderboards. `ciDelta`
  is the Elo 95% interval half-width, and lower WER is better.

```text
python data.py coding-agents --sort indexScore --fields displayLabel,indexScore,mean.costUsd --top 5
python data.py providers --model <model> --sort performance.outputSpeed --fields label,host.name,pricing
python data.py speech/sttModels --sort representativeHostModel.aaWerIndex --ascending
```

## Limits

- Models AA has not indexed yet and private evaluations are not covered.
- Prices outside OpenRouter and the AA catalog are not authoritative. Verify
  them with the provider.
