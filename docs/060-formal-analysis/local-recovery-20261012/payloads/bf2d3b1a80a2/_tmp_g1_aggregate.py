# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：NIR G1 关键判定量的全量聚合。

用途：在 G1 全量输出上聚合同步、可用性、buffer 损失、清洗轨道、固定时间箱支持、
geometry/R_seg 角色与 level/variability 可估计性，为正式参数冻结提供证据。
本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LINES: list[str] = []
OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_aggregate_out.txt")


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

    section("0. 运行清单要点")
    manifest = json.loads((root / "measurement_audit_manifest.json").read_text(encoding="utf-8"))
    for key in (
        "runner_version",
        "audit_schema_version",
        "status",
        "probe_window_sec",
        "blink_buffers",
        "fixed_bin_width_sec_candidates",
        "fixed_bin_candidates_are_formal_parameters",
        "cleaning_tracks",
        "main_signals",
        "soft_signal_role",
        "source_session_n_requested",
        "source_session_n_processed",
        "source_session_n_failed",
        "rgb_blink_source_available_session_n",
        "interpolation_used_for_formal_statistics",
        "q1_q2_used_for_parameter_selection",
    ):
        emit(f"{key}={json.dumps(manifest.get(key), ensure_ascii=False)}")
    failures = pd.read_csv(root / "measurement_audit_failures.csv")
    emit("failures=" + json.dumps(failures.to_dict("records"), ensure_ascii=False))

    section("1. RGB-NIR 同步")
    sync = pd.read_csv(root / "rgb_nir_sync_audit.csv")
    emit(f"sessions={len(sync)} sync_status={sync['sync_status'].value_counts(dropna=False).to_dict()}")
    emit(f"rgb_frame_axis_available={sync['rgb_frame_axis_available'].value_counts(dropna=False).to_dict()}")
    emit(f"rgb_blink_source_available={sync['rgb_blink_source_available'].value_counts(dropna=False).to_dict()}")
    emit(f"sync_evidence_level={sync['sync_evidence_level'].value_counts(dropna=False).to_dict()}")
    for column in (
        "frame_nearest_residual_abs_median_ms",
        "frame_nearest_residual_abs_p95_ms",
        "frame_nearest_residual_signed_median_ms",
        "frame_nearest_residual_abs_max_ms",
        "nir_frame_nominal_interval_ms",
        "rgb_frame_nominal_interval_ms",
        "nir_nonpositive_step_n",
        "rgb_frame_nonpositive_step_n",
    ):
        emit(f"{column}: {stats_of(sync[column])}")
    blink_sync = sync[sync["sync_status"] == "audited"]
    emit(f"blink_based_audited_sessions={len(blink_sync)}")
    emit(f"nearest_residual_abs_median_ms(audited): {stats_of(blink_sync['nearest_residual_abs_median_ms'])}")
    emit(f"nearest_residual_abs_p95_ms(audited): {stats_of(blink_sync['nearest_residual_abs_p95_ms'])}")
    emit(f"blink_event_n: {stats_of(sync['blink_event_n'], digits=5)}")

    section("2. 信号可用性（NIR QC）")
    avail = pd.read_csv(root / "signal_availability_audit.csv")
    emit(f"rows={len(avail)} sessions={avail['session_id'].nunique()}")
    group = avail.groupby(["eye", "signal"])["valid_fraction"]
    for (eye, signal), series in group:
        emit(f"eye={eye} signal={signal}: {stats_of(series, digits=4)}")
    session_signal = (
        avail.groupby(["session_id", "signal"])["valid_fraction"].mean().reset_index()
    )
    for signal, frame in session_signal.groupby("signal"):
        emit(f"session-mean valid_fraction signal={signal}: {stats_of(frame['valid_fraction'])}")

    section("3. 双眼来源模式")
    bino = pd.read_csv(root / "binocular_source_mode_audit.csv")
    emit(f"rows={len(bino)} sessions={bino['session_id'].nunique()}")
    emit(f"measurement_state={bino['measurement_state'].value_counts(dropna=False).to_dict()}")
    emit(f"source_mode={bino['source_mode'].value_counts(dropna=False).to_dict()}")
    pivot = bino.pivot_table(
        index=["session_id", "signal"], columns="source_mode", values="fraction", aggfunc="sum"
    ).reset_index()
    for signal, frame in pivot.groupby("signal"):
        emit(f"--- signal={signal}")
        for mode in ("binocular", "left_only", "right_only"):
            if mode in frame.columns:
                emit(f"  {mode}_fraction: {stats_of(frame[mode])}")

    section("4. 眨眼 buffer 损失")
    buf = pd.read_csv(root / "blink_buffer_loss_audit.csv")
    emit(f"rows={len(buf)} sessions={buf['session_id'].nunique()}")
    emit(f"buffer_ids={sorted(buf['buffer_id'].unique().tolist())}")
    for (buffer_id, signal), frame in buf.groupby(["buffer_id", "signal"]):
        emit(f"buffer={buffer_id} signal={signal}: {stats_of(frame['finite_lost_fraction'])}")
    no_blink = buf[buf["finite_before_blink_mask_n"] == 0]["session_id"].nunique()
    emit(f"sessions_with_zero_finite_before_blink={no_blink}")
    worst = (
        buf.sort_values("finite_lost_fraction", ascending=False)
        .head(15)[["session_id", "buffer_id", "signal", "finite_before_blink_mask_n", "finite_lost_fraction"]]
    )
    emit("worst_buffer_loss_rows=" + json.dumps(worst.to_dict("records"), ensure_ascii=False, default=str))

    section("5. 眨眼恢复轨迹支持")
    recovery = pd.read_csv(root / "blink_recovery_bins.csv")
    emit(f"rows={len(recovery)} sessions={recovery['session_id'].nunique()}")
    emit(f"anchors={recovery['anchor'].value_counts().to_dict()}")
    around = recovery[(recovery["relative_bin_center_ms"] >= -200) & (recovery["relative_bin_center_ms"] <= 200)]
    per_bin = around.groupby("relative_bin_center_ms")["nir_qc_valid_fraction"].mean()
    emit("mean_nir_qc_valid_fraction_by_bin_center_ms(-200..200)=" + json.dumps(
        {str(k): round(float(v), 4) for k, v in per_bin.items()}, ensure_ascii=False
    ))
    per_bin_raw = around.groupby("relative_bin_center_ms")["raw_computable_fraction"].mean()
    emit("mean_raw_computable_fraction_by_bin_center_ms=" + json.dumps(
        {str(k): round(float(v), 4) for k, v in per_bin_raw.items()}, ensure_ascii=False
    ))

    section("6. 固定时间箱与趋势支持")
    trajectories = pd.read_csv(root / "probe_fixed_bin_trajectories.csv")
    emit(f"rows={len(trajectories)} sessions={trajectories['session_id'].nunique()}")
    emit(f"bin_width_sec={sorted(trajectories['bin_width_sec'].unique().tolist())}")
    emit(f"cleaning_track={trajectories['cleaning_track'].value_counts().to_dict()}")
    emit(f"buffer_id={trajectories['buffer_id'].value_counts().to_dict()}")
    bin_summary = (
        trajectories.groupby(["cleaning_track", "bin_width_sec"])
        .agg(
            rows=("n_valid_samples", "size"),
            empty_bin_fraction=("n_valid_samples", lambda s: float((s == 0).mean())),
            bin_value_nonnull_fraction=("bin_value_median", lambda s: float(s.notna().mean())),
        )
        .reset_index()
    )
    emit("bin_summary=" + json.dumps(bin_summary.to_dict("records"), ensure_ascii=False))
    per_window = (
        trajectories.groupby(["cleaning_track", "bin_width_sec", "probe_event_id"])["n_valid_samples"]
        .apply(lambda s: int((s > 0).sum()))
        .reset_index()
        .rename(columns={"n_valid_samples": "n_valid_bins"})
    )
    emit("n_valid_bins_per_probe(1s bin, n bins defined=30): " + stats_of(per_window[per_window["bin_width_sec"] == 1.0]["n_valid_bins"], digits=4))
    emit("n_valid_bins_per_probe(5s bin, n bins defined=6): " + stats_of(per_window[per_window["bin_width_sec"] == 5.0]["n_valid_bins"], digits=4))

    section("7. level / variability / dynamics 可估计性")
    candidates = pd.read_csv(root / "probe_measurement_candidates.csv")
    emit(f"rows={len(candidates)} sessions={candidates['session_id'].nunique()}")
    emit(f"signals={candidates['signal'].unique().tolist()}")
    emit(f"signal_role={candidates.groupby(['signal', 'signal_role']).size().to_dict()}")
    emit(f"linear_status={candidates['linear_status'].value_counts(dropna=False).to_dict()}")
    emit(f"quadratic_status={candidates['quadratic_status'].value_counts(dropna=False).to_dict()}")
    for (track, signal), frame in candidates.groupby(["cleaning_track", "signal"]):
        emit(f"track={track} signal={signal} valid_fraction: {stats_of(frame['valid_fraction'])}")
        emit(f"track={track} signal={signal} level_median: {stats_of(frame['level_median'], digits=5)}")
        emit(f"track={track} signal={signal} variability_sd: {stats_of(frame['variability_sd'], digits=4)}")
    support = candidates.groupby(["cleaning_track", "signal"]).agg(
        early=("has_early_support", "mean"),
        late=("has_late_support", "mean"),
        span=("temporal_span_sec", "median"),
    )
    emit("support_by_track_signal=" + json.dumps(
        {f"{k[0]}|{k[1]}": {kk: round(float(vv), 4) for kk, vv in v.items()} for k, v in support.to_dict("index").items()},
        ensure_ascii=False,
    ))
    probe_key = ["session_id", "probe_event_id", "cleaning_track", "bin_width_sec"]
    emit(f"duplicate_keys={int(candidates.duplicated(probe_key).sum())}")

    section("8. geometry 与 R_seg 角色（含 n_pair 配对）")
    rseg = pd.read_csv(root / "rseg_measurement_sensitivity_audit.csv")
    emit(f"rows={len(rseg)} sessions={rseg['session_id'].nunique()}")
    emit(f"predictors={rseg['predictor'].unique().tolist()}")
    emit(f"roles={rseg['role'].unique().tolist()}")
    for predictor, frame in rseg.groupby("predictor"):
        emit(f"--- predictor={predictor}")
        emit(f"  n_pair: {stats_of(frame['n_pair'], digits=6)}")
        emit(f"  spearman_rho: {stats_of(frame['spearman_rho'])}")
        emit(f"  sessions_with_n_pair_zero={int((frame['n_pair'] == 0).sum())} of {len(frame)}")
        emit(f"  sessions_with_rho_missing={int(frame['spearman_rho'].isna().sum())}")
    emit("n_pair_zero_sessions=" + json.dumps(
        rseg[rseg["n_pair"] == 0].groupby("predictor")["session_id"].apply(list).to_dict(), ensure_ascii=False
    ))

    section("9. 探针覆盖与窗口")
    emit(f"probe_event_n={trajectories['probe_event_id'].nunique()}")
    emit(f"window_sec={sorted(trajectories['window_sec'].unique().tolist())}")
    emit(f"participant_group_n={trajectories['participant_group_id'].nunique()}")
    q = pd.read_csv(root / "probe_measurement_candidates.csv", usecols=["q1_nominal_4class", "q2_ordinal_4level"])
    emit(f"q1_nominal_4class={q['q1_nominal_4class'].value_counts(dropna=False).to_dict()}")
    emit(f"q2_ordinal_4level={q['q2_ordinal_4level'].value_counts(dropna=False).to_dict()}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
