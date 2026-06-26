# Changelog

All notable changes to which-llm will be documented in this file. Versioning
loosely follows [SemVer](https://semver.org/).

## Unreleased

### Added
- Atomic command scripts for pick, compare, profile, slug, frontier, and export
  flows.
- A shared command core for hidden snapshot readiness, presets, filters,
  formatting, frontier calculation, and artifact writing.
- Composable export field groups, including pricing plus context CSV output.
- `resolve.py` for natural model name resolution with selected slugs and
  alternates.
- API price filters separate from benchmark-run cost filters.
- Generic coding quality and API price filters for composable price-aware
  picks.
- Documented argument composition patterns for price-aware modality, coding,
  and context shortlists.
- Labeled nearest-result summaries for empty pick filters and opt-in export
  recovery.
- Exact `export.py --columns` selection plus a focused coding field group.
- Snapshot metadata in human-readable command output and artifact summaries.

### Changed
- Skill and README docs now present neutral capabilities instead of a
  status-first workflow.

## [0.4.0] - 2026-06-22

### Added
- Standalone `skills/which-llm` package for direct skill installs and skill
  marketplace indexing.
- Codex-native `.codex-plugin/plugin.json`, repo marketplace metadata, and
  skill UI metadata for the optional plugin wrapper.
- `indexTokensTotal` is now flattened into CSV output, emitted in JSON,
  shown as `idx-tok` in tables, and exposed through `--sort tokens`,
  `--max-index-tokens`, and `--min-index-tokens`.

### Changed
- `SKILL.md` is trimmed to the activation-critical workflow and command
  recipes.
- README now presents `which-llm` as an agent-agnostic skill first, with
  Codex plugin install as an optional wrapper.
- The refresh guard now compares against the tracked CSV snapshot.
- Tests moved out of the installed skill payload.
- Pareto chart labels preserve reasoning effort and non-reasoning variants
  when shortening model names.

### Removed
- Regenerable AA and OpenRouter refresh intermediates are no longer tracked,
  cutting the installed plugin payload by more than 12 MB.

## [0.3.1] - 2026-06-09

### Added
- `query.py compare <model>...` for side-by-side named model comparisons.
- `query.py slug <model>` for direct OpenRouter paid and free slug lookups.
- Compatibility aliases for older agent habits: `find`, `list`, `recommend`,
  `frontier`, `free`, `info`, `status`, and `refresh`.
- Ambiguity errors now include a concrete `models` command hint.
- Resolver tests for exact names, ambiguous matches, and duplicate
  OpenRouter endpoints.

## [0.3.0] - 2026-06-05

### Added
- Response-speed data: `ttft_seconds` (time to first answer token) and
  `e2e_response_seconds` (end-to-end latency) flattened from AA's metrics
  into the CSV, `show`, and `--json`.
- `--sort speed` (end-to-end latency, fastest first) and `--max-latency N`
  filter. An `e2e_s` column now appears in the `models` table.
- Unmeasured latency is normalized to null (AA emits an all-zero metrics
  dict for un-speed-tested models) so they don't masquerade as "fastest".

## [0.2.0] - 2026-05-23

**Breaking CLI redesign** (pre-release, no users depending on old surface yet).
The `find` / `list` / `recommend` / `frontier` / `free` subcommands are
collapsed into a single `models` verb. `info` becomes `show`. `status` / `refresh`
moved under a `data` namespace.

### Added
- `query.py models [<pattern>] [filters]`: one verb covers find / list /
  recommend / frontier / free. Same table schema for all queries.
- `--modality text,image,...` CSV flag replaces the asymmetric
  `--text/--image/--video/--audio` mix.
- `--reasoning/--no-reasoning` and `--open-weights/--no-open-weights` as
  proper tri-state `BooleanOptionalAction` flags (was a buggy lambda).
- `--json` output for every model-returning command.
- `query.py show <slug>`: annotates `:free` with a rate-limit caveat.
- Daily refresh workflow now opens a GitHub issue on failure (or comments
  on the existing open one) so silent decay surfaces.
- `artifacts/unmatched.txt` is committed; OR match-rate regressions show in
  git diffs.

### Changed
- GitHub Actions pinned to commit SHAs (was floating `@v3` / `@v4`),
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
