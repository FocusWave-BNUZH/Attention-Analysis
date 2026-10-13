"""Fit formal Q1/Q2 behavior models for the existing 10/20/30 s probe table."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from attention_pipeline.behavior_formal.science_v3 import (
    BehaviorScienceConfig,
    fit_probe_window_sensitivity_models,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_reference_match(
    observed: pd.DataFrame,
    reference: pd.DataFrame,
    keys: list[str],
) -> None:
    current = observed.loc[observed["window_seconds_nominal"] == 30].drop(
        columns="window_seconds_nominal"
    )
    merged = current.merge(reference, on=keys, how="outer", suffixes=("_window", "_formal"), indicator=True)
    if not merged["_merge"].eq("both").all():
        raise AssertionError("30 s model keys do not match the frozen formal table")
    for column in ("estimate_per_predictor_sd", "se", "ci_low", "ci_high"):
        if not np.allclose(
            merged[f"{column}_window"].to_numpy(float),
            merged[f"{column}_formal"].to_numpy(float),
            rtol=1e-9,
            atol=1e-10,
            equal_nan=True,
        ):
            raise AssertionError(f"30 s {column} differs from the frozen formal table")
    for column in ("participant_group_n", "session_n", "n_rows"):
        if not merged[f"{column}_window"].eq(merged[f"{column}_formal"]).all():
            raise AssertionError(f"30 s {column} differs from the frozen formal table")


def _write_atomic_csv(frame: pd.DataFrame, target: Path) -> None:
    partial = target.with_suffix(target.suffix + ".partial")
    frame.to_csv(partial, index=False, encoding="utf-8-sig")
    partial.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.formal_root.resolve()
    sensitivity_path = root / "probe_window_sensitivity.csv"
    q1_reference_path = root / "q1_nominal_models.csv"
    q2_reference_path = root / "q2_ordinal_gee_models.csv"
    started = time.monotonic()

    sensitivity = pd.read_csv(sensitivity_path, encoding="utf-8-sig")
    if len(sensitivity) != 6960:
        raise AssertionError(f"expected 6960 sensitivity rows, observed {len(sensitivity)}")
    if set(pd.to_numeric(sensitivity["window_seconds_nominal"], errors="raise").astype(int)) != {10, 20, 30}:
        raise AssertionError("expected sensitivity windows 10, 20, and 30 seconds")

    q1, q2, failures = fit_probe_window_sensitivity_models(
        sensitivity, BehaviorScienceConfig()
    )
    # Short windows can make variance-dependent metrics structurally unavailable.
    # Retain those fail-closed rows instead of fabricating estimates.
    if len(q1) + 3 * int((failures["outcome"] == "Q1").sum()) != 126:
        raise AssertionError(f"incomplete Q1 model accounting: results={len(q1)}, failures={len(failures)}")
    if len(q2) + int((failures["outcome"] == "Q2").sum()) != 42:
        raise AssertionError(f"incomplete Q2 model accounting: results={len(q2)}, failures={len(failures)}")
    if q1.duplicated(["window_seconds_nominal", "predictor", "contrast_category", "reference_category"]).any():
        raise AssertionError("duplicate Q1 sensitivity model keys")
    if q2.duplicated(["window_seconds_nominal", "predictor"]).any():
        raise AssertionError("duplicate Q2 sensitivity model keys")

    _assert_reference_match(
        q1, pd.read_csv(q1_reference_path, encoding="utf-8-sig"),
        ["model_name", "model_family", "outcome", "predictor", "contrast_category", "reference_category"],
    )
    _assert_reference_match(
        q2, pd.read_csv(q2_reference_path, encoding="utf-8-sig"),
        ["model_name", "model_family", "outcome", "predictor"],
    )

    q1_target = root / "probe_window_sensitivity_q1_models.csv"
    q2_target = root / "probe_window_sensitivity_q2_models.csv"
    failure_target = root / "probe_window_sensitivity_model_failures.csv"
    _write_atomic_csv(q1, q1_target)
    _write_atomic_csv(q2, q2_target)
    _write_atomic_csv(failures, failure_target)
    status = {
        "status": "PASS" if failures.empty else "PARTIAL",
        "input": str(sensitivity_path),
        "input_sha256": _sha256(sensitivity_path),
        "input_rows": int(len(sensitivity)),
        "windows_seconds": [10, 20, 30],
        "q1_rows": int(len(q1)),
        "q2_rows": int(len(q2)),
        "failure_rows": int(len(failures)),
        "failure_reason_counts": failures["reason"].value_counts().to_dict(),
        "thirty_second_reference_match": True,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    status_partial = root / "probe_window_sensitivity_model_status.json.partial"
    status_partial.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status_partial.replace(root / "probe_window_sensitivity_model_status.json")
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
