# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：buffer 与清洗轨道对探针级水平/波动的影响。

用途：比较 original_nir 与三种 buffer/清洗轨道在探针级 level_median、variability_sd 上的
差异（同探针配对），用于判断"最小充分 buffer"，而不是只看有效样本损失比例。
本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_buffer_effect_out.txt")
LINES: list[str] = []

KEY = ["session_id", "probe_event_id", "signal", "bin_width_sec"]
# 与 original_nir 比较的参考轨道（原样 NIR，含全部有效帧）
REFERENCE = ("original_nir", "none")


def emit(text: str) -> None:
    """打印并缓存一行结果。"""
    print(text)
    LINES.append(text)


def describe(series: pd.Series) -> str:
    """给出紧凑分位数摘要。"""
    clean = pd.Series(series).dropna()
    if clean.empty:
        return "empty"
    q = clean.quantile([0.0, 0.25, 0.5, 0.75, 0.95, 1.0])
    return (
        f"n={len(clean)} min={q.iloc[0]:.4g} p25={q.iloc[1]:.4g} M={q.iloc[2]:.4g} "
        f"p75={q.iloc[3]:.4g} p95={q.iloc[4]:.4g} max={q.iloc[5]:.4g}"
    )


def main() -> None:
    root = Path(
        r"D:\Project\.codex-worktrees\Attention-Analysis-1.16-g0-20260912\outputs\nir_pupil_blink_audit_g1_20260912_160556"
    )
    candidates = pd.read_csv(root / "probe_measurement_candidates.csv")
    emit(f"rows={len(candidates)}")

    reference = candidates[
        candidates["cleaning_track"].eq(REFERENCE[0]) & candidates["buffer_id"].eq(REFERENCE[1])
    ][KEY + ["level_median", "variability_sd", "valid_fraction", "n_valid_bins"]].rename(
        columns={
            "level_median": "ref_level",
            "variability_sd": "ref_sd",
            "valid_fraction": "ref_valid_fraction",
            "n_valid_bins": "ref_bins",
        }
    )

    for width in sorted(candidates["bin_width_sec"].unique().tolist()):
        emit("")
        emit(f"===== bin_width={width}s =====")
        frame = candidates[candidates["bin_width_sec"].eq(width)]
        merged = frame.merge(reference[reference["bin_width_sec"].eq(width)], on=KEY, how="left")
        for (track, buffer_id), group in merged.groupby(["cleaning_track", "buffer_id"]):
            if track == REFERENCE[0] and buffer_id == REFERENCE[1]:
                continue
            paired = group[group["ref_level"].notna() & group["level_median"].notna()].copy()
            paired["d_level"] = paired["level_median"] - paired["ref_level"]
            paired["d_sd"] = paired["variability_sd"] - paired["ref_sd"]
            paired["d_bins"] = paired["n_valid_bins"] - paired["ref_bins"]
            emit(
                f"track={track} buffer={buffer_id}: paired_n={len(paired)} "
                f"level_delta={describe(paired['d_level'])}"
            )
            emit(
                f"    sd_delta={describe(paired['d_sd'])}"
            )
            emit(
                f"    bin_delta={describe(paired['d_bins'])}"
            )

    emit("")
    emit("===== 探针级有效比例（含 buffer 维度，按场次聚合均值） =====")
    for (track, buffer_id), group in candidates.groupby(["cleaning_track", "buffer_id"]):
        per_session = group.groupby("session_id")["valid_fraction"].mean()
        emit(f"track={track} buffer={buffer_id}: session_mean_valid_fraction {describe(per_session)}")

    emit("")
    emit("===== level_median 缺失（不可估计）比例 =====")
    for (track, buffer_id), group in candidates.groupby(["cleaning_track", "buffer_id"]):
        emit(
            f"track={track} buffer={buffer_id}: level_missing_fraction="
            f"{float(group['level_median'].isna().mean()):.4f} "
            f"sd_missing_fraction={float(group['variability_sd'].isna().mean()):.4f}"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
