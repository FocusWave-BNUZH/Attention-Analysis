# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：量化 RGB 眨眼事件与 RGB 帧轴的时间错位。

用途：汇总事件被 RGB 帧轴支持的过滤丢弃的规模，判断这是全局对齐偏移还是来源缺失。
本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_aggregate7_out.txt")
LINES: list[str] = []


def emit(text: str) -> None:
    """打印并缓存一行结果。"""
    print(text)
    LINES.append(text)


def main() -> None:
    g1 = Path(
        r"D:\Project\.codex-worktrees\Attention-Analysis-1.16-g0-20260912\outputs\nir_pupil_blink_audit_g1_20260912_160556"
    )
    events = pd.read_csv(
        r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\RGB\11_analysis_tables\tables\rgb_blink_candidate_events.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )
    sync = pd.read_csv(g1 / "rgb_nir_sync_audit.csv")
    sync = sync.set_index("session_id")

    total_source = 0
    total_kept = 0
    dropped_sessions = 0
    rows: list[dict[str, object]] = []
    for session_id, group in events.groupby("session_id"):
        session_id = str(session_id)
        starts = pd.to_numeric(group["start_unix_ms"], errors="coerce")
        ends = pd.to_numeric(group["end_unix_ms"], errors="coerce")
        if session_id in sync.index:
            row = sync.loc[session_id]
            rgb_min, rgb_max = row["rgb_frame_time_min_ms"], row["rgb_frame_time_max_ms"]
            kept = int(((starts >= rgb_min) & (starts <= rgb_max)).sum()) if pd.notna(rgb_min) else 0
        else:
            kept = np.nan
        total_source += len(group)
        if not pd.isna(kept):
            total_kept += int(kept)
        if len(group) > 0 and kept == 0:
            dropped_sessions += 1
        rows.append(
            {
                "session_id": session_id,
                "source_events": len(group),
                "kept_in_rgb_axis": kept,
                "event_min": float(starts.min()),
                "event_max": float(starts.max()),
                "rgb_min": None if session_id not in sync.index else sync.loc[session_id, "rgb_frame_time_min_ms"],
                "rgb_max": None if session_id not in sync.index else sync.loc[session_id, "rgb_frame_time_max_ms"],
            }
        )

    emit(f"事件表总事件数={total_source} 落在 RGB 帧轴内={total_kept}")
    emit(f"整场事件全部被过滤的场次数={dropped_sessions}")
    summary = pd.DataFrame(rows)
    summary["event_min_minus_rgb_min_ms"] = summary["event_min"] - summary["rgb_min"]
    emit("event_min - rgb_min 分布: " + str(summary["event_min_minus_rgb_min_ms"].describe().round(1).to_dict()))
    emit("")
    emit("===== 事件全部被过滤的场次明细 =====")
    detail = summary[(summary["source_events"] > 0) & (summary["kept_in_rgb_axis"] == 0)]
    emit(detail.to_string(index=False, max_colwidth=30))
    emit("")
    emit("===== G1 中 15 个 no_blink_events 场次与事件表对照 =====")
    zero = sync[sync["sync_status"] == "no_blink_events"]
    for session_id in zero.index.tolist():
        has = session_id in set(events["session_id"].astype(str))
        n = int((events["session_id"].astype(str) == session_id).sum())
        emit(f"{session_id}: in_event_table={has} source_events={n} rgb_frame_axis={bool(sync.loc[session_id,'rgb_frame_axis_available'])}")
    emit("")
    emit("===== 全局帧轴起点关系（原样区间正负） =====")
    emit("rgb_minus_nir_start_ms 分布: " + str(pd.to_numeric(sync["rgb_minus_nir_start_ms"], errors="coerce").describe().round(1).to_dict()))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
