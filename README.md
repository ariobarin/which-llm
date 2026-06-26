# which-llm

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Daily refresh](https://img.shields.io/github/actions/workflow/status/ariobarin/which-llm/refresh.yml?label=daily%20refresh)](https://github.com/ariobarin/which-llm/actions/workflows/refresh.yml)
[![Last refresh](https://img.shields.io/github/last-commit/ariobarin/which-llm?label=last%20refresh)](https://github.com/ariobarin/which-llm/commits/main)

A lightweight agent skill for current LLM selection. It ships a compact Artificial Analysis plus OpenRouter snapshot and a plain Python CLI for model quality, price, speed, context, modality, and OpenRouter slug checks.

The primary package is `skills/which-llm`, so skill marketplaces can index the skill directly. Integration-specific wrappers live outside that package.

## Install The Skill Directly

Copy `skills/which-llm` into your agent host's configured skill directory.
Example for Codex user skills:

```bash
git clone https://github.com/ariobarin/which-llm /tmp/which-llm
CODEX_SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$CODEX_SKILLS_DIR"
cp -R /tmp/which-llm/skills/which-llm "$CODEX_SKILLS_DIR/"
```

Start a new agent session after installing, then ask normally:

```text
Which cheap vision model should I use?
Compare GPT-5, Claude, and Gemini for coding.
What is the OpenRouter slug for Claude Opus?
```

Requires Python 3.10+. No API keys are needed. First use is offline because the enriched CSV snapshot is checked in.

## Optional Plugin Wrapper

Codex users can also install through the plugin marketplace wrapper:

```text
codex plugin marketplace add ariobarin/which-llm --sparse .agents/plugins
codex plugin add which-llm@which-llm
```

The plugin wrapper exists only for Codex plugin marketplace discovery and install UX. The underlying package is the same `which-llm` skill.

## Atomic Commands

Run commands from `skills/which-llm`.

| Command | Produces |
|---|---|
| `python pick.py [preset] [filters]` | Ranked shortlist. |
| `python compare.py <model>...` | Side-by-side table. |
| `python profile.py <model>` | Model profile. |
| `python resolve.py <model>...` | Selected slugs plus alternates. |
| `python slug.py <model>` | Provider endpoint record. |
| `python frontier.py [preset] [filters]` | PNG chart plus CSV data. |
| `python export.py [preset] [filters]` | CSV or JSON file. |

Data readiness is handled inside each command. `query.py` and `plot_pareto.py`
remain available for compatibility.

Pick presets: `best`, `vision`, `long-context`, `open-weights`, `free`, and
`coding`.

Frontier presets: `cost-intel`, `speed-intel`, `tokens-intel`, `context-intel`,
`input-price-intel`, and `output-price-intel`.

Common filters: `--min-intel N`, `--max-run-cost N`, `--max-input-price N`,
`--max-output-price N`, `--min-context N`, `--max-latency N`,
`--modality text,image`, `--reasoning`, `--open-weights`, and `--free`.
`--max-cost` remains an alias for benchmark-run cost, not API price.
`pick.py` and `export.py` also accept `--top N` and
`--sort intel|cost|ctx|speed|tokens|coding|agentic|input-price|output-price`.
`pick.py` shows labeled nearest relaxations when no rows match; use
`--if-empty error` for strict empty-result failure.

Common behavior is built by composing presets, filters, and sorts:

```text
python pick.py best --min-intel 50 --sort cost --top 5
python pick.py best --min-intel 30 --sort speed --top 5
python pick.py vision --min-intel 40 --sort input-price --top 5
python pick.py coding --min-coding 45 --sort input-price --top 5
python pick.py long-context --min-intel 40 --sort input-price --top 5
python pick.py long-context --min-intel 40 --max-input-price N --sort input-price --top 5
```

Replace `N` with a price ceiling in USD per million input tokens.

Export field groups: `core`, `pricing`, `context`, `benchmarks`, `coding`,
`slugs`, and `full`. Groups can be combined with commas, such as
`--fields pricing,context`. Exact CSV columns can be selected with
`--columns name,openrouter_slug,coding_index`.
The `coding` group includes API prices, context, OpenRouter slugs, coding
scores, and coding benchmarks.

## Example

```text
$ python pick.py best --min-intel 50 --reasoning --sort tokens --top 3

| rank | model | slug | creator | intel | idx-run$ | idx-tok | in$/1m | out$/1m | ctx | e2e_s | openrouter |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | GPT-5.5 (medium) | gpt-5-5-medium | OpenAI | 50.4 | $869.91 | 127.5M | $5.00 | $30.00 | 922.0K | 20.5 | openai/gpt-5.5 |
| 2 | GPT-5.5 (high) | gpt-5-5-high | OpenAI | 53.1 | $1,655 | 209.3M | $5.00 | $30.00 | 922.0K | 39.2 | openai/gpt-5.5 |
| 3 | GPT-5.5 (xhigh) | gpt-5-5 | OpenAI | 54.8 | $2,630 | 295.5M | $5.00 | $30.00 | 922.0K | 115.9 | openai/gpt-5.5 |
```

`idx-run$` and `idx-tok` are benchmark-run proxies from Artificial Analysis, not per-call API pricing. For API pricing, use `in$/1m` and `out$/1m`.

OpenRouter `:free` slugs are prototype options. They can have rate limits, daily caps, weaker availability, or different serving details than paid endpoints.

## Data

Tracked runtime data:

| File | Contents |
|---|---|
| `skills/which-llm/artifacts/models_enriched.csv` | The compact AA plus OpenRouter snapshot used by the commands. |
| `skills/which-llm/artifacts/unmatched.txt` | Non-deprecated AA models without OpenRouter matches. |

Regenerable refresh intermediates such as `models.html`, `models.csv`, `models.json`, and `openrouter.json` are ignored to keep skill installs small.

## Development

```bash
git clone https://github.com/ariobarin/which-llm
cd which-llm
python -m pip install -e "skills/which-llm[test]"
python -m pytest tests -v
python skills/which-llm/pick.py best --top 3
```

Edit `skills/which-llm` first, then run `python scripts/sync_plugin_wrapper.py` to refresh the optional plugin wrapper. The mirror test fails if the wrapper drifts.

The daily GitHub Action refreshes the canonical skill snapshot, syncs the plugin wrapper, and commits CSV diffs when the public catalogs move.

## License

MIT. Data comes from public Artificial Analysis and OpenRouter pages.
