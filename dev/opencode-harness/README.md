# opencode Harness

This harness checks whether a fresh `opencode run` agent can use the local
which-llm skill without writing custom scripts.

It does not write global opencode config. The runner injects a session-scoped
`OPENCODE_CONFIG_CONTENT` value that adds this repo's `skills` directory to
opencode's skill search path.

```powershell
.\dev\opencode-harness\run-opencode-flow.ps1
```

Each case runs:

- `opencode run --format json`
- `--model bigmodel/glm-5.2`
- `--dangerously-skip-permissions`

Outputs are written to `dev\opencode-harness\outputs`. If opencode reports a
missing provider key, configure credentials with `opencode providers login` or
set the provider key expected by your local config, then rerun the harness.
