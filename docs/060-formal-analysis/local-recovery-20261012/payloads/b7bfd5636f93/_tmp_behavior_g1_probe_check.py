# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：Behavior formal_v3 的 RT 中心趋势与探针结构检查。

用途：为 Behavior 116 场冻结决策提供描述性证据（mean RT vs median RT 冗余度与覆盖）。
说明：本机 scipy.stats.spearmanr 会触发原生崩溃（0xc06d007f），因此 Spearman 相关
改用等价的秩变换 + Pearson 实现，公式与审计表所用版本一致。
本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\Behavior\formal_v3")
OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_behavior_check_out.txt")
LINES: list[str] = []


def emit(text: str) -> None:
    """同时打印并缓存一行结果，避免管道编码问题导致输出丢失。"""
    print(text)
    LINES.append(text)


def average_rank(values: np.ndarray) -> np.ndarray:
    """用纯 NumPy 计算平均秩，避免 scipy/pandas 排序内核在本机触发的原生崩溃。"""
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks_sorted = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start
        while end + 1 < len(values) and sorted_values[end + 1] == sorted_values[start]:
            end += 1
        ranks_sorted[start : end + 1] = (start + end) / 2.0 + 1.0
        start = end + 1
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = ranks_sorted
    return ranks


def spearman_safe(a: pd.Series, b: pd.Series) -> float:
    """用平均秩 + Pearson 计算 Spearman 相关系数（等价于 scipy.spearmanr 的统计量）。"""
    frame = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(frame) < 3:
        return float("nan")
    ra = average_rank(frame["a"].to_numpy(dtype=float))
    rb = average_rank(frame["b"].to_numpy(dtype=float))
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> None:
    session = pd.read_csv(ROOT / "session_metrics.csv")
    mean = session["go_correct_rt_mean_ms"]
    median = session["go_correct_rt_median_ms"]
    pair = mean.notna() & median.notna()

    emit(f"sessions_total={len(session)}")
    emit(f"mean_coverage={int(mean.notna().sum())} median_coverage={int(median.notna().sum())}")
    emit(f"pair_n={int(pair.sum())}")
    emit(f"spearman_session={spearman_safe(mean, median):.4f}")

    diff = (mean - median)[pair]
    emit(
        "mean_minus_median_M={:.2f} SD={:.2f} median={:.2f} min={:.2f} max={:.2f}".format(
            diff.mean(), diff.std(), diff.median(), diff.min(), diff.max()
        )
    )
    emit(f"mean_M={mean[pair].mean():.2f} mean_SD={mean[pair].std():.2f}")
    emit(f"median_M={median[pair].mean():.2f} median_SD={median[pair].std():.2f}")

    probe = pd.read_csv(ROOT / "probe_primary_30s.csv")
    emit(f"probe_rows={len(probe)} sessions={probe['session_id'].nunique()}")
    emit(f"probe_windows={sorted(probe['window_seconds_nominal'].dropna().unique().tolist())}")
    emit(f"probe_metric_units={probe['metric_units'].dropna().unique().tolist()}")
    emit(f"probe_spearman_mean_median={spearman_safe(probe['go_correct_rt_mean_ms'], probe['go_correct_rt_median_ms']):.4f}")

    # 探针层面按窗口分别检查冗余度，确认主窗口与敏感性窗口结论一致。
    for window in sorted(probe["window_seconds_nominal"].dropna().unique().tolist()):
        sub = probe[probe["window_seconds_nominal"] == window]
        emit(
            "probe_window={}s n={} spearman={:.4f}".format(
                window, len(sub), spearman_safe(sub["go_correct_rt_mean_ms"], sub["go_correct_rt_median_ms"])
            )
        )

    qc = pd.read_csv(ROOT / "qc_denominators.csv")
    emit(f"qc_denominators_cols={list(qc.columns)}")
    emit("qc_denominators_head=" + json.dumps(qc.head(10).to_dict("records"), ensure_ascii=False, default=str))

    status = pd.read_csv(ROOT / "behavior_sensitivity_status.csv")
    emit(f"sensitivity_status_cols={list(status.columns)}")
    emit("sensitivity_status=" + json.dumps(status.to_dict("records"), ensure_ascii=False, default=str)[:1200])

    manifest = json.loads((ROOT / "run_manifest.json").read_text(encoding="utf-8"))
    for key in (
        "probe_primary_rows",
        "primary_probe_window_seconds",
        "sensitivity_probe_windows_seconds",
        "run_status",
        "rt_cv_min_n",
        "rt_slope_min_n",
        "model_failure_rows",
        "candidate_validation_rows",
        "omission_validation_rows",
        "endpoint_decision_rows",
        "study_total_scope_contract",
        "candidate_selection_contract",
        "formal_inference_contract",
    ):
        emit(f"manifest.{key}={json.dumps(manifest.get(key), ensure_ascii=False)[:700]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
