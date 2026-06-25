# Claude Harness

This harness checks whether a fresh `claude -p` agent can use the local
which-llm plugin without writing custom scripts.

It loads the plugin from this checkout only:

```powershell
.\dev\claude-harness\run-claude-flow.ps1
```

Each case starts a new no-persistence `claude -p` run with:

- `--plugin-dir plugins\which-llm`
- `--output-format stream-json`
- `--verbose`
- `--tools Read,Bash`

Outputs are written to `dev\claude-harness\outputs`. The script prints a small
summary with the atomic scripts observed in each run.

If the configured Claude provider returns 401, reauthenticate first and rerun
the harness. The plugin can load before the provider token is accepted.
