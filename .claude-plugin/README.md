# Legacy marketplace metadata

Codex uses `.agents/plugins/marketplace.json` and
`plugins/which-llm/.codex-plugin/plugin.json` as the primary install surface.

This directory remains for legacy-compatible plugin clients that still read
`.claude-plugin/marketplace.json`.

Keep the version in `marketplace.json` aligned with:

- `plugins/which-llm/.codex-plugin/plugin.json`
- `plugins/which-llm/.claude-plugin/plugin.json`
- `plugins/which-llm/skills/which-llm/pyproject.toml`
- `CHANGELOG.md`
