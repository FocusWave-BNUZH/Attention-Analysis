## Scope

This PR fixes the current G1 post-processing failure mode without changing the measurement producer or freezing scientific parameters.

- adds a signal-aware G1 decision-summary module and CLI for existing audit CSVs;
- keeps `signal × cleaning_track × buffer_id × bin_width_sec` separate so 30 s windows cannot be reported as 90/45/18 valid bins by summing three signals;
- keeps binocular `measurement_state` separate so source fractions cannot exceed 1 by combining `raw_computable` and `nir_qc_valid`;
- keeps blink recovery `anchor=start/end` separate;
- adds fail-closed validation for impossible per-signal bin counts;
- adds regression tests for the summary dimensions;
- adds a regression test documenting the already-correct missing-RGB contract: a missing RGB session file is unavailable, not zero blinks. NIR-only tracks remain governed by the existing runner logic.

## Important non-change

The current integration runner already handles a genuinely missing RGB frame file as `None` and continues NIR-only (`original_nir` / `nir_qc_only`) outputs. Therefore this PR does **not** introduce a false core-logic fix for `sub-041`; it only locks that behavior with a test.

## Intended local follow-up

After CI, rerun only the new summary CLI against the existing G1 output directory. No RITnet/NIR full-cohort rerun is required by these changes.
