---
name: which-llm
description: Choose current LLMs by quality, price, speed, context, modality, or OpenRouter slug. Use for model recommendations, model comparisons, pricing checks, and code changes that add or swap an LLM.
---

# which-llm

Use this skill when model knowledge may be stale. It queries a checked-in Artificial Analysis plus OpenRouter snapshot and can refresh it on demand.

## Workflow

1. Run commands from this directory with `python`.
2. If freshness matters, run `python query.py data status`. If the snapshot is stale, run `python query.py data refresh`.
3. Use the narrowest command:
   - `python query.py models [pattern] [filters]` for shortlists.
   - `python query.py compare <model>...` for side-by-side comparisons.
   - `python query.py slug <model>` for OpenRouter endpoint names.
   - `python query.py show <model>` before recommending a specific model.
4. Explain cost fields correctly:
   - `idx-run$` is the effective estimated cost to run the AA benchmark suite.
   - A plain `idx-run$` value is published by AA. A `~` prefix means which-llm estimated it from `idx-tok * out$/1m`.
   - Use `idx-run$` as the default price metric for value, ranking, and frontier decisions.
   - `idx-tok` is total benchmark-run token use.
   - `in$/1m` and `out$/1m` are API prices per million tokens.
   - Use per-million token prices for provider billing display or explicit billing calculations, not as the default frontier axis.
5. Prefer `openrouter_slug` for production. Mention `openrouter_free_slug` only as a prototype option because `:free` endpoints can be rate-limited or served differently.

## Fast Recipes

```text
python query.py models --intel-min 50 --reasoning --sort cost --top 8
python query.py models --modality text,image --max-cost 500 --sort intel --top 8
python query.py models --no-reasoning --max-latency 6 --sort intel --top 8
python query.py models --context-min 256000 --sort cost --top 8
python query.py models --open-weights --sort intel --top 8
python query.py models --free --sort cost --top 20
python query.py compare claude-opus-4-7 gpt-5 gemini-3-1-pro
python query.py slug claude-opus-4-7
```

Use `python query.py models --help` for all filters, including `--json`.

## Do Not Use For

- Domain evals or private benchmarks that AA does not track.
- Models so new that AA has not indexed them yet.
- Authoritative non-OpenRouter provider pricing. Verify those prices with the provider.
