# which-llm

A Claude Code skill that gives your agent up-to-date data on ~520 LLMs:
intelligence scores, cost-to-run, benchmark breakdowns, capabilities, and
OpenRouter slugs (including which ones have a `:free` tier).

Trained-in model knowledge goes stale within months. This skill scrapes
[artificialanalysis.ai](https://artificialanalysis.ai/models) on demand and
cross-references it with the OpenRouter catalog, so when you ask Claude
"which model should I use for X" you get an answer based on this week's
landscape rather than last year's.

## Install

### Via Claude Code plugin marketplace (recommended)

```text
/plugin marketplace add ariobarin/which-llm
/plugin install which-llm@which-llm
```

That's it. Auto-updates when this repo gets a new release.

### Direct (no plugin system)

```bash
git clone https://github.com/ariobarin/which-llm /tmp/which-llm
cp -r /tmp/which-llm/plugins/which-llm/skills/which-llm ~/.claude/skills/which-llm
```

Requirements: Python 3.10+ and [`uv`](https://docs.astral.sh/uv/). The skill
ships a recent data snapshot so it works immediately; run
`uv run py query.py refresh` from the skill directory to update.

## Demo

Ask Claude any of these and the skill should activate:

> *"I need a vision model under $500 with reasoning. What are my options?"*
>
> *"Is there a free version of DeepSeek V4 Flash on OpenRouter?"*
>
> *"What's the cheapest model with an intelligence index above 50?"*
>
> *"Compare GPT-5.5, Claude Opus 4.7, and Gemini 3.1 Pro on cost vs intelligence."*

Under the hood it runs short `query.py` commands. For example:

```
$ uv run py query.py recommend --intel-min 50 --max-cost 1000 --image --limit 5

slug                    name                    creator  intel  cost     ctx       free  openrouter
----------------------  ----------------------  -------  -----  -------  --------  ----  -----------------------------
grok-4-3                Grok 4.3 (high)         xAI      53.2   $395.17  1000000   -     x-ai/grok-4.3
gpt-5-5-low             GPT-5.5 (low)           OpenAI   50.8   $500.67   922000   -     openai/gpt-5.5
gemini-3-1-pro-preview  Gemini 3.1 Pro Preview  Google   57.2   $892.28  1000000   -     google/gemini-3.1-pro-preview
kimi-k2-6               Kimi K2.6               Kimi     53.9   $947.87   256000   -     moonshotai/kimi-k2.6
gpt-5-5-medium          GPT-5.5 (medium)        OpenAI   56.7  $1,199.   922000   -     openai/gpt-5.5
```

## Commands

| Command | Use |
|---|---|
| `query.py status` | Data freshness, model count, OR enrichment status |
| `query.py refresh` | Re-scrape AA + re-cross-reference OR (~10s) |
| `query.py find <pattern>` | Substring match on name / slug / creator |
| `query.py info <slug>` | Full info for one model |
| `query.py list [--limit N] [--by-cost] [--max-cost N]` | Top N |
| `query.py frontier` | Cost-vs-intelligence Pareto frontier |
| `query.py recommend --intel-min N --max-cost M [...]` | Best fit |
| `query.py free` | All `:free` OR models |

All commands accept modality filters: `--text` (default), `--no-text`,
`--image`, `--video`, `--audio`, `--free`. They AND together.

For visual exploration there's also `plot_pareto.py` which renders the
Intelligence-vs-Cost Pareto chart.

## What gets cached

| File | Contents |
|---|---|
| `artifacts/models.csv` | 60-column flat per-model rows |
| `artifacts/models.json` | Full original AA fields (every benchmark, every modality flag) |
| `artifacts/models_enriched.csv` | Same as `models.csv` plus OpenRouter slugs / free flag |
| `artifacts/openrouter.json` | Raw OpenRouter catalog |

## Refresh policy

The skill ships a recent snapshot. Run `query.py refresh` weekly, or before
any pricing-sensitive decision. `query.py status` warns when data is older
than 7 days.

## When NOT to use

- Benchmarks Artificial Analysis doesn't track (domain-specific evals).
- Models too new for AA to have indexed yet (<1 week post-release sometimes).
- For an authoritative per-API-call price on a non-OR provider — verify
  directly with that provider.

## License

MIT. See `LICENSE`.

## Credits

Data from [Artificial Analysis](https://artificialanalysis.ai) and
[OpenRouter](https://openrouter.ai). This skill scrapes both public pages /
APIs and does not require credentials.
