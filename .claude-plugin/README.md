# Legacy marketplace metadata

The primary package is the standalone skill at `skills/which-llm`.
Codex can also use `.agents/plugins/marketplace.json` and
`plugins/which-llm/.codex-plugin/plugin.json` as a light plugin wrapper.

This directory remains for legacy-compatible plugin clients that still read
`.claude-plugin/marketplace.json`.

Keep the version in `marketplace.json` aligned with:

- `plugins/which-llm/.codex-plugin/plugin.json`
- `plugins/which-llm/.claude-plugin/plugin.json`
- `skills/which-llm/pyproject.toml`
- `CHANGELOG.md`
