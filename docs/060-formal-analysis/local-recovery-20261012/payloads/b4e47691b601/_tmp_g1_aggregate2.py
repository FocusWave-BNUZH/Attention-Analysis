# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：G1 主键、时间箱支持、眨眼恢复与失败场次定位。

用途：修正上一版聚合口径（buffer 维度被误并入分母），给出可据以冻结的最小充分 buffer、
固定时间箱与趋势支持证据，并定位失败场次与 aperture 配对缺失的来源。
本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LINES: list[str] = []
OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_aggregate2_out.txt")


def emit(text: str) -> None:
    """同时打印并缓存一行结果，避免控制台编码问题导致输出丢失。"""
    print(text)
    LINES.append(text)


def section(title: str) -> None:
    emit("")
    emit(f"===== {title} =====")


def stats_of(series: pd.Series, digits: int = 4) -> str:
    """给出紧凑的分位数摘要，便于判断分布而不是只看均值。"""
    clean = pd.Series(series).dropna()
    if clean.empty:
        return "empty"
    q = clean.quantile([0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0])
    return (
        f"n={len(clean)} min={q.iloc[0]:.{digits}g} p05={q.iloc[1]:.{digits}g} "
        f"p25={q.iloc[2]:.{digits}g} M={q.iloc[3]:.{digits}g} p75={q.iloc[4]:.{digits}g} "
        f"p95={q.iloc[5]:.{digits}g} max={q.iloc[6]:.{digits}g} mean={clean.mean():.{digits}g}"
    )


def main() -> None:
    root = Path(sys.argv[1])

    section("A. 候选表主键与维度")
    candidates = pd.read_csv(root / "probe_measurement_candidates.csv")
    emit(f"rows={len(candidates)}")
    for keys in (
        ["session_id", "probe_event_id", "signal"],
        ["session_id", "probe_event_id", "signal", "cleaning_track"],
        ["session_id", "probe_event_id", "signal", "cleaning_track", "bin_width_sec"],
        ["session_id", "probe_event_id", "signal", "cleaning_track", "bin_width_sec", "buffer_id"],
    ):
        emit(f"dup({'+'.join(keys)})={int(candidates.duplicated(keys).sum())}")
    emit(f"buffer_id_values={candidates['buffer_id'].value_counts(dropna=False).to_dict()}")
    emit(f"bin_width_values={candidates['bin_width_sec'].value_counts(dropna=False).to_dict()}")
    emit(f"cleaning_track_values={candidates['cleaning_track'].value_counts(dropna=False).to_dict()}")
    emit(f"signal_values={candidates['signal'].value_counts(dropna=False).to_dict()}")

    section("B. 轨迹表结构（含空箱是否落盘）")
    trajectories = pd.read_csv(root / "probe_fixed_bin_trajectories.csv")
    emit(f"rows={len(trajectories)}")
    for keys in (
        ["session_id", "probe_event_id", "signal", "cleaning_track", "buffer_id", "bin_width_sec", "bin_index"],
    ):
        emit(f"dup({'+'.join(keys)})={int(trajectories.duplicated(keys).sum())}")
    emit(f"probe_event_rows={trajectories['probe_event_id'].nunique()} sessions={trajectories['session_id'].nunique()}")
    emit(f"rows_with_zero_valid_samples={int((trajectories['n_valid_samples'] == 0).sum())}")
    emit(f"bin_value_median_missing={int(trajectories['bin_value_median'].isna().sum())}")
    counts = (
        trajectories.groupby(["cleaning_track", "buffer_id", "bin_width_sec", "probe_event_id"])
        .size()
        .reset_index(name="n_rows")
    )
    emit("n_rows_per_probe_by_track_buffer_binwidth=" + json.dumps(
        counts.groupby(["cleaning_track", "buffer_id", "bin_width_sec"])["n_rows"].agg(["min", "median", "max"]).reset_index().to_dict("records"),
        ensure_ascii=False,
    ))
    valid = (
        trajectories[trajectories["bin_value_median"].notna()]
        .groupby(["cleaning_track", "buffer_id", "bin_width_sec", "probe_event_id"])
        .size()
        .reset_index(name="n_valid_bins")
    )
    for (track, buffer_id, width), frame in valid.groupby(["cleaning_track", "buffer_id", "bin_width_sec"]):
        defined = int(round(30.0 / width))
        emit(
            f"track={track} buffer={buffer_id} width={width}s defined_bins={defined} "
            f"n_valid_bins: {stats_of(frame['n_valid_bins'], digits=4)}"
        )
        emit(
            f"   fraction_of_probes_with_full_support={float((frame['n_valid_bins'] == defined).mean()):.4f} "
            f"fraction_with_zero_support={float((frame['n_valid_bins'] == 0).mean()):.4f}"
        )

    section("C. 最低时间支持（趋势可估计）")
    for (track, buffer_id), frame in candidates.groupby(["cleaning_track", "buffer_id"]):
        emit(
            f"track={track} buffer={buffer_id} n={len(frame)} "
            f"linear_computable={float((frame['linear_status'] == 'computable').mean()):.4f} "
            f"quadratic_computable={float((frame['quadratic_status'] == 'computable').mean()):.4f} "
            f"early={float(frame['has_early_support'].mean()):.4f} late={float(frame['has_late_support'].mean()):.4f}"
        )
    for (track, buffer_id, width), frame in candidates.groupby(["cleaning_track", "buffer_id", "bin_width_sec"]):
        emit(
            f"width={width}s track={track} buffer={buffer_id} "
            f"n_valid_bins: {stats_of(frame['n_valid_bins'], digits=4)} "
            f"temporal_span: {stats_of(frame['temporal_span_sec'], digits=4)}"
        )

    section("D. 眨眼恢复：逐箱 NIR QC 有效性")
    recovery = pd.read_csv(root / "blink_recovery_bins.csv")
    emit(f"rows={len(recovery)} sessions={recovery['session_id'].nunique()}")
    for signal, frame in recovery.groupby("signal"):
        around = frame[(frame["relative_bin_center_ms"] >= -250) & (frame["relative_bin_center_ms"] <= 250)]
        per_bin = around.groupby("relative_bin_center_ms")["nir_qc_valid_fraction"].mean()
        emit(f"signal={signal} mean_nir_qc_valid_fraction_by_center_ms=" + json.dumps(
            {str(k): round(float(v), 4) for k, v in per_bin.items()}, ensure_ascii=False
        ))
        per_bin_raw = around.groupby("relative_bin_center_ms")["raw_computable_fraction"].mean()
        emit(f"signal={signal} mean_raw_computable_fraction_by_center_ms=" + json.dumps(
            {str(k): round(float(v), 4) for k, v in per_bin_raw.items()}, ensure_ascii=False
        ))
        # 量化"接近零有效性"的时窗宽度，用于判断最小充分 buffer。
        near_zero = per_bin[per_bin < 0.20]
        emit(f"signal={signal} bins_with_mean_nir_qc_valid_fraction<0.20=" + json.dumps(
            {str(k): round(float(v), 4) for k, v in near_zero.items()}, ensure_ascii=False
        ))

    section("E. 失败场次 sub-041 来源定位")
    failures = pd.read_csv(root / "measurement_audit_failures.csv")
    emit("failures=" + json.dumps(failures.to_dict("records"), ensure_ascii=False))
    rgb_root = Path(r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\RGB\10_analysis_ready")
    for path in sorted(rgb_root.rglob("sub-041*")):
        emit(f"rgb_artifact={path} size={path.stat().st_size if path.is_file() else 'dir'}")
    for path in sorted(rgb_root.rglob("*sub-041*")):
        emit(f"rgb_artifact_nested={path}")

    section("F. R_seg 与 geometry 配对字段的来源覆盖")
    rseg = pd.read_csv(root / "rseg_measurement_sensitivity_audit.csv")
    emit(f"predictors={sorted(rseg['predictor'].unique().tolist())}")
    emit("n_pair_by_predictor=" + json.dumps(
        rseg.groupby("predictor")["n_pair"].agg(["min", "median", "max", "mean"]).round(2).reset_index().to_dict("records"),
        ensure_ascii=False,
    ))
    emit("n_pair_zero_predictors=" + json.dumps(
        rseg.groupby("predictor")["n_pair"].apply(lambda s: int((s == 0).sum())).to_dict(), ensure_ascii=False
    ))
    emit("rho_missing_by_predictor=" + json.dumps(
        rseg.groupby("predictor")["spearman_rho"].apply(lambda s: int(s.isna().sum())).to_dict(), ensure_ascii=False
    ))
    # 检查 aperture 字段是否在 NIR analysis-ready 来源中存在
    nir_root = Path(r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\NIR\10_analysis_ready")
    hit = []
    for path in sorted(nir_root.rglob("*.csv"))[:400]:
        hit.append(str(path.relative_to(nir_root)))
    emit(f"nir_analysis_ready_csv_n={len(hit)}")
    emit("nir_analysis_ready_first20=" + json.dumps(hit[:20], ensure_ascii=False))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
