# which-llm

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Daily refresh](https://img.shields.io/github/actions/workflow/status/ariobarin/which-llm/refresh.yml?label=daily%20refresh)](https://github.com/ariobarin/which-llm/actions/workflows/refresh.yml)

An agent skill that answers "which LLM should I use?" with current data instead of training-data guesses. It bundles a daily snapshot of [Artificial Analysis](https://artificialanalysis.ai) benchmarks and [OpenRouter](https://openrouter.ai) model IDs, plus small Python commands your agent runs to filter, compare, and chart models by quality, price, speed, context, and modality.

No API keys. Python 3.10+ standard library only (charts also need matplotlib).

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

The plugin has no version number, so it tracks commits. To pull the latest, run `claude plugin marketplace update which-llm` and then `claude plugin update which-llm@which-llm`.

Codex plugin:

```bash
codex plugin marketplace add ariobarin/which-llm
codex plugin add which-llm@which-llm
```

Manual: copy `skills/which-llm` into your agent's skills directory.

</details>

## Use

Start a new agent session and ask normally:

```text
Which cheap vision model should I use?
Compare the top OpenAI, Anthropic, and Google models for coding.
What's the OpenRouter slug for this model? Is there a free one?
Plot cost vs intelligence for open-weight models.
```

The agent picks the right command. You can also run them yourself from `skills/which-llm`:

```text
$ python pick.py vision --min-intel 40 --sort input-price --top 3

| rank | model | creator | intel | intel-task$ | in$/1m | out$/1m | ctx | openrouter |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | GPT-6.1 Terra (Max) | OpenAI | 51.3 | $0.96 | $1.00 | $5.00 | 1.0M | openai/gpt-6.1-terra |
| 2 | GPT-6.1 Terra (Xhigh) | OpenAI | 45.3 | $0.40 | $1.00 | $5.00 | 1.0M | openai/gpt-6.1-terra |
| 3 | GPT-6.1 Terra (High) | OpenAI | 42.4 | $0.26 | $1.00 | $5.00 | 1.0M | openai/gpt-6.1-terra |
```

(Some columns trimmed. Output from November 2026.)

[SKILL.md](skills/which-llm/SKILL.md) lists every command and explains the cost columns. Every command takes `--help`.

## How the data stays fresh

A GitHub Action scrapes AA and OpenRouter daily and publishes to the `automation/daily-data-refresh` branch. Installed skills fetch from there when their local copy is more than two days old, so new models show up without reinstalling. If the fetch fails, commands say so instead of answering from stale data.

The skill does not cover models AA has not benchmarked yet, private evals, or non-OpenRouter provider pricing.

## Development

The skill lives in `skills/which-llm`. The Claude Code and Codex plugin manifests at the repo root both point at that one copy.

```bash
git clone https://github.com/ariobarin/which-llm
cd which-llm
python -m pip install cryptography pytest matplotlib
python -m pytest tests
```

`scrape.py` reads the Next.js RSC stream on AA pages and decrypts the dataset manifests it finds; `enrich.py` adds OpenRouter slugs. When AA changes their site the daily refresh opens an issue. Run `python skills/which-llm/scrape.py --refresh`, read the error, fix the parser, and add a test in `tests/which_llm/test_scrape.py`.

## License

MIT. Data comes from public [Artificial Analysis](https://artificialanalysis.ai) and [OpenRouter](https://openrouter.ai) pages; credit them when you share results.
