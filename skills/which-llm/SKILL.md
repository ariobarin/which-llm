---
name: which-llm
description: Choose current LLMs by quality, price, speed, context, modality, or OpenRouter slug. Use for model recommendations, model comparisons, pricing checks, and code changes that add or swap an LLM.
---

# which-llm

This skill provides a current Artificial Analysis plus OpenRouter snapshot and
small Python commands for model selection data. Data readiness is internal to
each command: cached data is used immediately, missing data is created
automatically, and stale data only prints a warning.

Run commands from this skill directory with `python`, or call scripts by path
with `${CLAUDE_SKILL_DIR}` in Claude Code.

## Capabilities

| Capability | Command | Produces |
|---|---|---|
| Pick ranked models from constraints | `python pick.py [preset] [filters]` | Ranked shortlist |
| Compare named models | `python compare.py <model>...` | Side-by-side table |
| Inspect one model | `python profile.py <model>` | Model profile |
| Resolve endpoint names | `python slug.py <model>` | Provider endpoint record |
| Generate tradeoff frontier | `python frontier.py [preset] [filters]` | PNG chart plus CSV data |
| Export filtered rows | `python export.py [preset] [filters]` | CSV or JSON file |

`query.py` and `plot_pareto.py` remain available for compatibility, but the
atomic commands above are the fastest surface for normal use.

## Pick Presets

| Preset | Meaning |
|---|---|
| `best` | Highest intelligence. |
| `cheap-good` | Intelligence at least 50, ranked by benchmark-run cost. |
| `cheap-vision` | Image-capable models with intelligence at least 40, ranked by input price. |
| `fast-good` | Useful quality, ranked by end to end latency. |
| `vision` | Text and image capable models. |
| `long-context` | Context window at least 256K tokens. |
| `open-weights` | Open-weight models. |
| `free` | Models with OpenRouter free prototype endpoints. |
| `coding` | Ranked by Artificial Analysis coding index. |

## Frontier Presets

| Preset | X metric | Y metric |
|---|---|---|
| `cost-intel` | Benchmark-run cost, minimized | Intelligence, maximized |
| `speed-intel` | End to end latency, minimized | Intelligence, maximized |
| `tokens-intel` | Benchmark-run tokens, minimized | Intelligence, maximized |
| `context-intel` | Context window, maximized | Intelligence, maximized |
| `input-price-intel` | Input price per 1M, minimized | Intelligence, maximized |
| `output-price-intel` | Output price per 1M, minimized | Intelligence, maximized |

## Shared Filters

`pick.py`, `frontier.py`, and `export.py` share these filters:

```text
--pattern TEXT
--creator NAME
--reasoning / --no-reasoning
--open-weights / --no-open-weights
--free
--text / --no-text
--image
--video
--audio
--modality text,image
--min-intel N
--max-cost N
--min-context N
--max-latency N
--max-index-tokens N
--min-index-tokens N
```

`pick.py` and `export.py` also accept `--sort` with `intel`, `cost`, `ctx`,
`tokens`, `speed`, `coding`, `agentic`, `input-price`, or `output-price`.
They also accept `--top N`.

`export.py` accepts `--fields core`, `pricing`, `context`, `benchmarks`,
`slugs`, or `full`. Field groups can be combined with commas, such as
`--fields pricing,context`.

## Output Notes

- `idx-run$` is the estimated cost to run the Artificial Analysis benchmark
  suite. It is not a per-call API price.
- `idx-tok` is total benchmark-run token use.
- `in$/1m` and `out$/1m` are API prices per million tokens.
- `openrouter_slug` is the production endpoint name.
- `openrouter_free_slug` is a prototype option. Free endpoints can be
  rate-limited or served differently from paid listings.

## Examples

```text
python pick.py cheap-good --image --top 8
python pick.py cheap-vision --top 5
python compare.py gpt-5-5-medium glm-5-2
python profile.py glm-5-2
python slug.py glm-5-2
python frontier.py cost-intel --max-x 1200 --out-dir artifacts
python export.py open-weights --fields pricing,context --format csv
```

## Do Not Use For

- Domain evals or private benchmarks that Artificial Analysis does not track.
- Models so new that Artificial Analysis has not indexed them yet.
- Authoritative non-OpenRouter provider pricing. Verify those prices with the
  provider.
