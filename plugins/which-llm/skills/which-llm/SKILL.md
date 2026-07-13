---
name: which-llm
description: Inspect current LLM tradeoffs across quality, price, speed, context, modality, and OpenRouter availability. Use for model recommendations, comparisons, pricing checks, and code changes that add or swap an LLM.
---

# which-llm

This skill provides a current Artificial Analysis plus OpenRouter snapshot and
small Python commands for model selection data. Data readiness is internal to
each command: cached data is used immediately, missing data is created
automatically, and stale or undated data stops recommendations until refreshed.

Run commands from this skill directory with `python`, or call scripts by path
with `${CLAUDE_SKILL_DIR}` in Claude Code.

## Capabilities

| Capability | Command | Produces |
|---|---|---|
| Inspect ranked models under constraints | `python pick.py [preset] [filters]` | Ranked evidence table |
| Compare named models | `python compare.py <model>...` | Side-by-side table |
| Inspect one model | `python profile.py <model>` | Model profile |
| Resolve natural names | `python resolve.py <model>...` | Selected slugs plus alternates |
| Resolve endpoint names | `python slug.py <model>` | Provider endpoint record |
| Generate Pareto frontier | `python frontier.py [preset] [filters]` | PNG chart plus CSV data |
| Export filtered rows | `python export.py [preset] [filters]` | CSV or JSON file |

`query.py` and `plot_pareto.py` remain available for compatibility, but the
atomic commands above are the fastest surface for normal use.

## Evidence, Not Conclusions

The commands organize current evidence. They do not choose a model for the
agent or user. A default sort order is not a recommendation.

- Start with the user's stated constraints and objective.
- Present relevant tradeoffs, scope, and uncertainty before a conclusion.
- Recommend a model only when the user asks for a recommendation. State the
  objective that produced it.
- If the user requests a different metric or weighting, show that view without
  treating the earlier view as universally correct.

## Cost Context

Token prices are rates. They do not establish workload or task cost without the
input and output token volumes. Caching, tool calls, reasoning tokens, retries,
and model behavior can materially change total spend.

- Do not use a blended token price as workload-cost evidence. A blend assumes a
  token mix that may have no relationship to the user's workload.
- `intel-task$` and `agent-task$` are benchmark-specific task-cost evidence.
  They are not estimates of the user's application spend.
- `idx-run$` is the cost of a full benchmark run. It is not a per-call price.
- When useful, show benchmark task cost and input and output token rates side by
  side, with each scope labeled.
- If a user asks why token price was not used, explain the rate versus workload
  distinction and offer a direct rate-only comparison.
- Calculate a workload estimate only when token volume, cache behavior, tool
  use, and retry assumptions are available. Label every assumption.

## Pick Presets

| Preset | Meaning |
|---|---|
| `best` | Highest intelligence. |
| `vision` | Text and image capable models. |
| `long-context` | Context window at least 256K tokens. |
| `open-weights` | Open-weight models. |
| `free` | Models with OpenRouter free prototype endpoints. |
| `coding` | Ranked by Artificial Analysis coding index. |

## Frontier Presets

| Preset | X metric | Y metric |
|---|---|---|
| `cost-intel` | Intelligence Index cost per task, minimized | Intelligence, maximized |
| `agentic-cost` | Agentic Index cost per task, minimized | Agentic Index, maximized |
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
--max-run-cost N
--max-input-price N
--max-output-price N
--min-context N
--min-coding N
--max-latency N
--max-index-tokens N
--min-index-tokens N
```

`--max-cost` remains an alias for `--max-run-cost`, the benchmark-run cost.
Use `--max-input-price` or `--max-output-price` for API price per 1M tokens.
A benchmark frontier must pair each score with that same benchmark's cost per
task. The commands reject known cross-benchmark cost and score pairs.

`pick.py` and `export.py` also accept `--sort` with `intel`, `cost`, `ctx`,
`tokens`, `speed`, `coding`, `agentic`, `input-price`, or `output-price`.
They also accept `--top N`.
`pick.py` shows clearly labeled one-filter relaxations when no rows match.
Use `--if-empty error` for strict empty-result failure. `export.py` accepts
`--if-empty nearest` for the same labeled recovery without writing a relaxed
data file.

`compare.py` resolves strictly by default. It accepts `--resolve auto` when
selecting the strongest ambiguous match and listing alternates is acceptable.

`export.py` accepts `--fields core`, `pricing`, `context`, `benchmarks`,
`coding`, `slugs`, or `full`. Field groups can be combined with commas, such
as `--fields pricing,context`. Exact columns can be selected with
`--columns name,openrouter_slug,coding_index`.

## Useful Argument Compositions

These are ordinary command shapes built from presets, filters, and sorts.
Replace `N` with a price ceiling in USD per million input tokens.

| Behavior | Command shape |
|---|---|
| Intelligence-task cost efficiency | `python pick.py best --min-intel 50 --sort cost --top 5` |
| Fast quality shortlist | `python pick.py best --min-intel 30 --sort speed --top 5` |
| Low input-price shortlist | `python pick.py best --min-intel 40 --sort input-price --top 5` |
| Low-price image-capable shortlist | `python pick.py vision --min-intel 40 --sort input-price --top 5` |
| Price-aware coding shortlist | `python pick.py coding --min-coding 45 --sort input-price --top 5` |
| Long-context ranked by input price | `python pick.py long-context --min-intel 40 --sort input-price --top 5` |
| Long-context under input-price budget | `python pick.py long-context --min-intel 40 --max-input-price N --sort input-price --top 5` |
| Low output-price shortlist | `python pick.py best --max-output-price 5 --sort output-price --top 5` |
| Strict no-match behavior | `python pick.py vision --free --min-intel 70 --if-empty error` |
| Nearest no-match evidence | `python pick.py vision --free --min-intel 70 --top 5` |

## Export Field Groups

| Field group | Contains |
|---|---|
| `core` | Main quality, cost, context, speed, and OpenRouter columns. |
| `pricing` | Benchmark-run cost, token use, API prices, cache price, and slugs. |
| `context` | Context window, modalities, reasoning, open weights, and slug. |
| `coding` | API prices, context, OpenRouter slugs, coding scores, and coding benchmarks. |
| `benchmarks` | Intelligence, coding, agentic, math, and benchmark scores. |
| `slugs` | Internal slug, OpenRouter production slug, and free slug. |
| `full` | All tracked columns. |

## Output Notes

- Every command emits a compact cost-scope reminder for the calling agent.
- Default profiles omit legacy blended-rate fields. Explicit full exports retain
  the source columns for inspection.
- `idx-run$` is the estimated cost to run the Artificial Analysis benchmark
  suite. It is not a per-call API price.
- `intel-task$` and `agent-task$` are the matching weighted benchmark costs per
  task. `--sort cost` sorts by `intel-task$`.
- `intelligence_index_cost_per_task_usd` is the weighted Intelligence Index cost
  per task.
- `agentic_index_cost_per_task_usd` is the weighted Agentic Index cost per task.
- `idx-tok` is total benchmark-run token use.
- `in$/1m` and `out$/1m` are API prices per million tokens.
- `openrouter_slug` is the production endpoint name.
- `openrouter_free_slug` is a prototype option. Free endpoints can be
  rate-limited or served differently from paid listings.

## Examples

```text
python pick.py best --min-intel 50 --sort cost --image --top 8
python pick.py vision --min-intel 40 --sort input-price --top 5
python pick.py coding --min-coding 45 --sort input-price --top 5
python pick.py long-context --min-intel 40 --sort input-price --top 5
python compare.py gpt-5-5-medium glm-5-2
python resolve.py "gemini flash" "gpt nano"
python profile.py glm-5-2
python slug.py glm-5-2
python frontier.py cost-intel --max-x 1200 --out-dir artifacts
python frontier.py agentic-cost --image --out-dir artifacts
python export.py open-weights --fields pricing,context --format csv
python export.py open-weights --reasoning --fields coding --format csv
```

## Do Not Use For

- Domain evals or private benchmarks that Artificial Analysis does not track.
- Models so new that Artificial Analysis has not indexed them yet.
- Authoritative non-OpenRouter provider pricing. Verify those prices with the
  provider.
