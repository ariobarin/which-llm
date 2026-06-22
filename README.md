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

## Commands

Run commands from `skills/which-llm`.

| Command | Use |
|---|---|
| `python query.py models [pattern] [filters]` | List or rank models. |
| `python query.py compare <model>...` | Compare named models. |
| `python query.py slug <model>` | Return paid and free OpenRouter slugs. |
| `python query.py show <model>` | Inspect one model before recommending it. |
| `python query.py data status` | Check snapshot age and model count. |
| `python query.py data refresh` | Rebuild local AA and OpenRouter data. |

Common filters: `--top N`, `--sort intel|cost|ctx|speed|tokens`, `--intel-min N`, `--max-cost N`, `--context-min N`, `--max-latency N`, `--modality text,image`, `--reasoning`, `--open-weights`, `--free`, `--json`.

## Example

```text
$ python query.py models --intel-min 50 --reasoning --sort tokens --top 3

slug                    name                    creator  intel  idx-run$  idx-tok  in$/1m  out$/1m  ctx      e2e_s  free  openrouter
----------------------  ----------------------  -------  -----  --------  -------  ------  -------  -------  -----  ----  -----------------------------
gpt-5-5-low             GPT-5.5 (low)           OpenAI   50.8   $500.67   65.1M    $5.00   $30.00   922000   12.1         openai/gpt-5.5
gpt-5-5-medium          GPT-5.5 (medium)        OpenAI   56.7   $1,199    127.5M   $5.00   $30.00   922000   18.7         openai/gpt-5.5
gemini-3-1-pro-preview  Gemini 3.1 Pro Preview  Google   57.2   $892.28   159.7M   $2.00   $12.00   1000000  26.3         google/gemini-3.1-pro-preview
```

`idx-run$` and `idx-tok` are benchmark-run proxies from Artificial Analysis, not per-call API pricing. For API pricing, use `in$/1m` and `out$/1m`.

OpenRouter `:free` slugs are prototype options. They can have rate limits, daily caps, weaker availability, or different serving details than paid endpoints.

## Data

Tracked runtime data:

| File | Contents |
|---|---|
| `skills/which-llm/artifacts/models_enriched.csv` | The compact AA plus OpenRouter snapshot used by `query.py`. |
| `skills/which-llm/artifacts/unmatched.txt` | Non-deprecated AA models without OpenRouter matches. |

Regenerable refresh intermediates such as `models.html`, `models.csv`, `models.json`, and `openrouter.json` are ignored to keep skill installs small.

## Development

```bash
git clone https://github.com/ariobarin/which-llm
cd which-llm
python -m pip install -e "skills/which-llm[test]"
python -m pytest tests -v
python skills/which-llm/query.py models --top 3
```

Edit `skills/which-llm` first, then run `python scripts/sync_plugin_wrapper.py` to refresh the optional plugin wrapper. The mirror test fails if the wrapper drifts.

The daily GitHub Action refreshes the canonical skill snapshot, syncs the plugin wrapper, and commits CSV diffs when the public catalogs move.

## License

MIT. Data comes from public Artificial Analysis and OpenRouter pages.
