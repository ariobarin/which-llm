# Plugin marketplace metadata

This directory declares the repo as a Claude Code **plugin marketplace** so
users can install which-llm with:

```text
/plugin marketplace add Doomsy1/which-llm
/plugin install which-llm@Doomsy1
```

## Maintenance

1. Bump `version` in `marketplace.json` whenever you cut a release. Keep it
   in sync with `pyproject.toml` and the top of `CHANGELOG.md`.
2. If `/plugin marketplace add` ever starts rejecting the file, the plugin
   schema has likely evolved — check the current Claude Code plugin docs
   and update field names here.

If you don't want the plugin route, this directory is harmless — the
`git clone …/.claude/skills/which-llm` install flow works without it.
