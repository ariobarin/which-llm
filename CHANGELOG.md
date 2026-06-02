# Changelog

All notable changes to which-llm will be documented in this file. Versioning
loosely follows [SemVer](https://semver.org/).

## [0.3.0] - 2026-06-01

Layered data sourcing + attribution. The dataset is now built from three
sources merged by `build.py`, and the project credits its sources explicitly.

### Added
- `fetch_api.py` — pulls Artificial Analysis's official free API
  (`/api/v2/data/llms/models`) using `AA_API_KEY`. Authoritative
  benchmarks/pricing keyed by stable UUIDs.
- `build.py` — orchestrates scrape (primary) + AA API (cross-check/fallback)
  + OpenRouter (availability) into `models_enriched.csv`, with an
  `intelligence_index` drift cross-check between scrape and API.
- `WHICH_LLM_SOURCE=merged|scrape|api` env switch. `merged` (default)
  degrades to an API-built base if the scrape parser breaks, so the dataset
  is never empty. `api` builds from the sanctioned API only (no scraping).
- `enrich.py` now also extracts OpenRouter `context_length`,
  `input_modalities`, and a reasoning signal (gap-fill / cross-check).
- `query.py` emits the required Artificial Analysis attribution (to stderr,
  so stdout/`--json` stay clean) and links each model's AA page in `show`.
- README "Data, attribution & usage" section: source credit, the
  code-vs-data license split, and a takedown/comply contact.

### Changed
- Daily refresh workflow runs `build.py --refresh` with an `AA_API_KEY` repo
  secret and commits `models_api.json` alongside the other artifacts.
- `idx-run$` (cost to run AA's Intelligence Index) reframed as the headline
  "intelligence per dollar" metric throughout the docs.

## [0.2.0] - 2026-05-23

**Breaking CLI redesign** (pre-release, no users depending on old surface yet).
The `find` / `list` / `recommend` / `frontier` / `free` subcommands are
collapsed into a single `models` verb. `info` → `show`. `status` / `refresh`
moved under a `data` namespace.

### Added
- `query.py models [<pattern>] [filters]` — one verb covers find / list /
  recommend / frontier / free. Same table schema for all queries.
- `--modality text,image,...` CSV flag replaces the asymmetric
  `--text/--image/--video/--audio` mix.
- `--reasoning/--no-reasoning` and `--open-weights/--no-open-weights` as
  proper tri-state `BooleanOptionalAction` flags (was a buggy lambda).
- `--json` output for every model-returning command.
- `query.py show <slug>` — annotates `:free` with a rate-limit caveat.
- Daily refresh workflow now opens a GitHub issue on failure (or comments
  on the existing open one) so silent decay surfaces.
- `artifacts/unmatched.txt` is committed; OR match-rate regressions show in
  git diffs.

### Changed
- GitHub Actions pinned to commit SHAs (was floating `@v3` / `@v4`) —
  closes the cheapest supply-chain pivot.
- `scrape.py` now anchors the `defaultData` parser to a multi-key
  signature and asserts schema (>= 400 items with required keys) before
  overwriting the snapshot.
- Retry/backoff on AA and OpenRouter fetches (3 attempts, exp backoff on
  5xx).
- OR catalog sorted by id before indexing so multi-variant matches don't
  flap day-to-day.
- README leads with install above the demo block; `:free` caveat is now
  explicit ("rate-limited promo listing, prototyping only").

### Removed
- Old subcommands `find`, `list`, `recommend`, `frontier`, `free`,
  `info`, `status` (top-level), `refresh` (top-level). Migration is
  mechanical; see the new SKILL.md commands table.

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
