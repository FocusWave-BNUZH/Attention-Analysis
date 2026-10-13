## Scope

This PR fixes the current G1 post-processing failure mode without changing the measurement producer or freezing scientific parameters.

- adds a signal-aware G1 decision-summary module and CLI for existing audit CSVs;
- keeps `signal × cleaning_track × buffer_id × bin_width_sec` separate so 30 s windows cannot be reported as 90/45/18 valid bins by summing three signals;
- keeps binocular `measurement_state` separate so source fractions cannot exceed 1 by combining `raw_computable` and `nir_qc_valid`;
- keeps blink recovery `anchor=start/end` separate;
- adds fail-closed validation for impossible per-signal bin counts;
- adds regression tests for the summary dimensions;
- adds a regression test documenting the missing-RGB contract;
- adds non-fatal degradation for a **present-but-corrupt** RGB frame table (see below).

## RGB source contract (corrected 2026-09-13)

Two distinct RGB cases must not be conflated:

1. **Genuinely missing RGB frame file** — already handled before this PR:
   `load_session_rgb_blink_frames()` returns `None` when the root is `None` or the
   per-session parquet is absent. This PR locks that behavior with a regression test.
2. **Present-but-corrupt RGB frame file** — newly handled by this PR:
   a file that exists but cannot be parsed previously raised inside the per-session
   block, which aborted the whole session and discarded otherwise valid
   `original_nir` / `nir_qc_only` measurements. The runner now wraps
   `load_session_rgb_blink_frames()` in `try/except`, sets `rgb_frames = None`, and
   records a row in the new `measurement_audit_warnings.csv`
   (`stage = rgb_blink_frame_source`). The session then continues and produces its
   NIR-only tracks.

## Scope (runner changes)

- `RUNNER_VERSION` bumped `nir-pupil-blink-measurement-audit-runner-v1` → `-v2`;
- new `measurement_audit_warnings.csv` (columns: `session_id`, `stage`, `warning_type`, `warning`) written by `_tables()`;
- manifest carries `source_session_n_warning` and `source_warning_sessions`.

## Validation on real data

109-session G1 cohort, code identity `c2d36ad`:

`source_session_n_requested = 109`, `source_session_n_processed = 109`,
`source_session_n_failed = 0`, `source_session_n_warning = 1` — `sub-041`,
`ArrowInvalid`: "Parquet magic bytes not found in footer".

`sub-041` is absent from `measurement_audit_failures.csv` and retains 360 rows in
`probe_measurement_candidates.csv` and 6,120 rows in
`probe_fixed_bin_trajectories.csv`, with
`sync_status = rgb_blink_source_unavailable` in `rgb_nir_sync_audit.csv`.

## Intended local follow-up

After CI: rerun only the summary CLI against the existing G1 output directory.
No RITnet/NIR full-cohort rerun is required by the summary changes. The 109-session
measurement audit has already been rerun once on `c2d36ad` and is archived as
`NIR_G1_20260912_fixed`.
