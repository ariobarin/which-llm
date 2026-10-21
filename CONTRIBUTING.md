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

`scrape.py` reads the Next.js RSC stream on AA pages, finds the encrypted
dataset manifests, and decrypts them. If AA changes their site, the daily
refresh opens an issue. To fix:

1. Run `python skills/which-llm/scrape.py --refresh` and read the error.
2. Inspect `skills/which-llm/artifacts/models.html` for the new structure.
3. Update `scrape.py` and add a test in `tests/which_llm/test_scrape.py`.
4. Check that the 20% row-drop guard and schema checks still pass.

## Versioning

Bump `version` in these files when cutting a release, and update
`CHANGELOG.md`:

- `skills/which-llm/pyproject.toml`
- `plugins/which-llm/.codex-plugin/plugin.json`
- `plugins/which-llm/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

## Code style

No rigid rules. Match what's there. No comments unless the why is non-obvious.
