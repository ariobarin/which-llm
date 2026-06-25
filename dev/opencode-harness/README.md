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
missing provider key, the current shell cannot see the key expected by your
local config. This checkout's observed config uses `{env:BIGMODEL_API_KEY}` for
the BigModel provider, so run the harness from an environment where that
variable is set, then rerun it.

To load a local env file for the harness process without printing secrets:

```powershell
.\dev\opencode-harness\run-opencode-flow.ps1 -EnvFile C:\path\to\.env
```
