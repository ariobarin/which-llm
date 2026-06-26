# Contributing

Thanks for considering a contribution.

## Quick setup

```bash
git clone https://github.com/ariobarin/which-llm
cd which-llm
python -m pip install -e "skills/which-llm[test]"
python -m pytest tests -v
```

## What lives where

| Path | Purpose |
|---|---|
| `skills/which-llm/` | Canonical skill package: instructions, scripts, and data |
| `plugins/which-llm/skills/which-llm/` | Optional plugin wrapper mirror of the skill package |
| `tests/which_llm/` | Repo tests, kept out of install packages |
| `scripts/sync_plugin_wrapper.py` | Refreshes the plugin wrapper from the canonical skill |
| `plugins/which-llm/.codex-plugin/` | Codex plugin manifest |
| `.agents/plugins/` | Codex repo marketplace metadata |
| `.github/workflows/refresh.yml` | Daily data refresh cron |
| `README.md`, `CHANGELOG.md` | Repo-level docs |
| `.claude-plugin/` | Legacy-compatible marketplace metadata |
| `dev/` | One-off exploration scripts (not part of the shipped skill) |

Keep `skills/which-llm` agent-agnostic. Put platform-specific wording only in
integration wrappers and install docs.

## Making changes

1. Create a branch.
2. Make runtime changes inside `skills/which-llm/`.
3. Run `python scripts/sync_plugin_wrapper.py`.
4. Run `python -m pytest tests -v`; all tests must pass.
5. If you changed command behavior, run `python skills/which-llm/pick.py best --top 3`.
6. Open a PR. Describe what changed and why.

## Parser changes

`scrape.py` parses an 8 MB HTML page by regex-matching Next.js RSC chunks.
If AA changes their page structure, this will break. To fix:

1. Download the new page: `python scrape.py --refresh`
2. Inspect `artifacts/models.html` for the new structure.
3. Update the regex / anchor in `scrape.py`.
4. Add or update a test in `tests/test_scrape.py` for the new pattern.
5. Verify the catastrophic-drop guard and schema assertions still pass.

## Versioning

Bump `version` in all three places when cutting a release:
- `plugins/which-llm/.codex-plugin/plugin.json`
- `plugins/which-llm/.claude-plugin/plugin.json`
- `skills/which-llm/pyproject.toml`
- `.claude-plugin/marketplace.json`

Update `CHANGELOG.md` with the changes.

## Code style

No rigid rules. Match what's there. No comments unless the why is non-obvious.
