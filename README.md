# which-llm

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Daily refresh](https://img.shields.io/github/actions/workflow/status/ariobarin/which-llm/refresh.yml?label=daily%20refresh)](https://github.com/ariobarin/which-llm/actions/workflows/refresh.yml)

An agent skill that answers "which LLM should I use?" with current data instead of training-data guesses. It bundles a daily snapshot of [Artificial Analysis](https://artificialanalysis.ai) benchmarks and [OpenRouter](https://openrouter.ai) model IDs, plus small Python commands your agent runs to filter, compare, and chart models by quality, price, speed, context, and modality.

No API keys. Python 3.10+ standard library only.

## Install

Any agent that supports [Agent Skills](https://agentskills.io) (Claude Code, Codex, Cursor, Gemini CLI, and more):

```bash
npx skills add ariobarin/which-llm
```

Add `-g` to install for all projects instead of the current one.

<details>
<summary>Other ways to install</summary>

Claude Code plugin:

```text
/plugin marketplace add ariobarin/which-llm
/plugin install which-llm@which-llm
```

Codex plugin:

```bash
codex plugin marketplace add ariobarin/which-llm --sparse .agents/plugins --sparse plugins/which-llm
codex plugin add which-llm@which-llm
```

Manual: copy `skills/which-llm` into your agent's skills directory.

</details>

## Use

Start a new agent session and ask normally:

```text
Which cheap vision model should I use?
Compare GPT-5.5, Claude Opus, and Gemini for coding.
What's the OpenRouter slug for GLM-5.2? Is there a free one?
Plot cost vs intelligence for open-weight models.
```

The agent picks the right command. You can also run them yourself from `skills/which-llm`:

```text
$ python pick.py vision --min-intel 40 --sort input-price --top 3

| rank | model | creator | intel | intel-task$ | in$/1m | out$/1m | ctx | openrouter |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Claude Haiku 5.5 (Xhigh) | Anthropic | 41.2 | $0.12 | $0.10 | $0.50 | 1.0M | anthropic/claude-haiku-5.5 |
| 2 | Claude Haiku 5.5 (Max) | Anthropic | 43.4 | $0.21 | $0.10 | $0.50 | 1.0M | anthropic/claude-haiku-5.5 |
| 3 | GLM-5.3-Flash | Z AI | 41.8 | $0.28 | $0.15 | $0.50 | 1.0M | z-ai/glm-5.3-flash |
```

(Some columns trimmed.)

| Command | What it does |
|---|---|
| `pick.py [preset] [filters]` | Ranked shortlist. Presets: `best`, `vision`, `long-context`, `open-weights`, `free` |
| `compare.py <model>...` | Side-by-side table |
| `profile.py <model>` | Everything about one model |
| `resolve.py <name>...` | Natural name to exact slug, with alternates |
| `slug.py <model>` | OpenRouter paid and `:free` IDs |
| `frontier.py [preset]` | Pareto chart (PNG) plus CSV. Needs `pip install matplotlib` |
| `export.py [preset] [filters]` | CSV or JSON file |
| `data.py [dataset]` | Raw AA datasets: evaluations, capabilities, coding agents, media, speech |

Every command takes `--help`. [SKILL.md](skills/which-llm/SKILL.md) has the full filter and field reference.

### Reading the numbers

- `in$/1m` and `out$/1m` are API prices per million tokens. They are rates, not what your workload will cost.
- `intel-task$` is AA's measured cost per Intelligence Index task. It folds in how many tokens a model actually spends, so it is the better "cost to get an answer" signal.
- `idx-run$` is the cost of AA's whole benchmark run, not a per-call price.
- OpenRouter `:free` endpoints are for prototyping. Expect rate limits.

## How the data stays fresh

A GitHub Action scrapes AA and OpenRouter daily and publishes to the `automation/daily-data-refresh` branch. Installed skills fetch from there when their local copy is more than two days old, so new models show up without reinstalling. If the fetch fails, commands say so instead of answering from stale data.

The skill does not cover models AA has not benchmarked yet, private evals, or non-OpenRouter provider pricing.

## Development

```bash
git clone https://github.com/ariobarin/which-llm
cd which-llm
python -m pip install -e "skills/which-llm[test]"
python -m pytest tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for layout and the refresh pipeline.

## License

MIT. Data comes from public [Artificial Analysis](https://artificialanalysis.ai) and [OpenRouter](https://openrouter.ai) pages; credit them when you share results.
