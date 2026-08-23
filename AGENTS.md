# a-stock-lib repository rules

This repository owns reusable market-data Provider primitives shared by `a-stock-tracker` and `a-stock-agent-skills`. Current code and tests are authoritative. Read `README.md` for the current package surface, the relevant document under `docs/design/` for architecture decisions, and `docs/RELEASE_CHECKLIST.md` only for release work.

## Boundaries

- Keep changes inside this repository unless the user separately authorizes a consumer-repository change.
- Never hardcode or commit credentials. Keep real network access out of tests; inject clients and keep optional third-party SDK imports lazy.
- Provider boundaries translate external failures into structured `MarketDataResult` outcomes with an explicit status and error code; do not leak SDK exception types to consumers.
- Preserve source, timestamp/freshness, degradation, and fallback metadata. Point-in-time gaps such as suspensions or holidays must use the established nearest-valid-date semantics rather than silently presenting stale data as current.
- Persistent cache writes must be atomic. Reuse the existing temporary-file, flush/fsync, and replace pattern.
- Do not add a dependency without explicit approval and corresponding project metadata.

## Verification

Use the commands declared by `README.md` and `pyproject.toml`. Run the affected tests during development, then the proportionate repository checks and `git diff --check` before handoff. Release and downstream-consumer validation belong to `docs/RELEASE_CHECKLIST.md`, not every code change.
