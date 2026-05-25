# Contributing

Thanks for considering a contribution.

## Quick setup

```bash
git clone https://github.com/ariobarin/which-llm
cd which-llm/plugins/which-llm/skills/which-llm
uv sync
uv run pytest tests/ -v
```

## What lives where

| Path | Purpose |
|---|---|
| `plugins/which-llm/skills/which-llm/` | The skill: scripts, data, tests |
| `.github/workflows/refresh.yml` | Daily data refresh cron |
| `README.md`, `CHANGELOG.md` | Repo-level docs |
| `.claude-plugin/` | Plugin marketplace metadata |
| `dev/` | One-off exploration scripts (not part of the shipped skill) |

## Making changes

1. Create a branch.
2. Make your changes inside `plugins/which-llm/skills/which-llm/`.
3. Run `uv run pytest tests/ -v` — all tests must pass.
4. If you changed `query.py`, run a quick `uv run python query.py models --top 3` to verify.
5. Open a PR. Describe what you changed and why.

## Parser changes

`scrape.py` parses an 8 MB HTML page by regex-matching Next.js RSC chunks.
If AA changes their page structure, this will break. To fix:

1. Download the new page: `uv run python scrape.py --refresh`
2. Inspect `artifacts/models.html` for the new structure.
3. Update the regex / anchor in `scrape.py`.
4. Add or update a test in `tests/test_scrape.py` for the new pattern.
5. Verify the catastrophic-drop guard and schema assertions still pass.

## Versioning

Bump `version` in all three places when cutting a release:
- `plugins/which-llm/.claude-plugin/plugin.json`
- `plugins/which-llm/skills/which-llm/pyproject.toml`
- `.claude-plugin/marketplace.json`

Update `CHANGELOG.md` with the changes.

## Code style

No rigid rules. Match what's there. No comments unless the *why* is non-obvious.
