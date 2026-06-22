# Legacy marketplace metadata

The primary package is the standalone skill at `skills/which-llm`.
Platform wrappers live outside that package. Codex uses
`.agents/plugins/marketplace.json` plus
`plugins/which-llm/.codex-plugin/plugin.json`, while this directory remains for
legacy-compatible plugin clients that still read `.claude-plugin/marketplace.json`.

Keep the version in `marketplace.json` aligned with:

- `plugins/which-llm/.codex-plugin/plugin.json`
- `plugins/which-llm/.claude-plugin/plugin.json`
- `skills/which-llm/pyproject.toml`
- `CHANGELOG.md`
