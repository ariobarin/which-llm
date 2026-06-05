# Changelog

All notable changes to which-llm will be documented in this file. Versioning
loosely follows [SemVer](https://semver.org/).

## [0.3.0] - 2026-06-05

### Added
- Response-speed data: `ttft_seconds` (time to first answer token) and
  `e2e_response_seconds` (end-to-end latency) flattened from AA's metrics
  into the CSV, `show`, and `--json`.
- `--sort speed` (end-to-end latency, fastest first) and `--max-latency N`
  filter. An `e2e_s` column now appears in the `models` table.
- Unmeasured latency is normalized to null (AA emits an all-zero metrics
  dict for un-speed-tested models) so they don't masquerade as "fastest".
- `--creator a,b` filter (CSV substrings, case-insensitive, matched against
  creator name/slug) and `--list-creators` to discover the roster. AA has no
  country field, so geography is filtered by naming labs rather than baked in.

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
