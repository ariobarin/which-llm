# Changelog

All notable changes to which-llm will be documented in this file. Versioning
loosely follows [SemVer](https://semver.org/).

## [0.1.0] - 2026-05-23

Initial release.

- `query.py` agent-facing CLI with `status`, `refresh`, `find`, `info`,
  `list`, `frontier`, `recommend`, `free` subcommands.
- `scrape.py` parses the RSC payload from artificialanalysis.ai/models and
  extracts all ~520 models with full schema.
- `enrich.py` cross-references the OpenRouter catalog for slugs and
  `:free` availability. Current match rate ~51%.
- `plot_pareto.py` renders an Intelligence-vs-Cost Pareto chart with
  modality and free-tier filters.
- Ships a baseline data snapshot in `artifacts/` for instant cold-start.
