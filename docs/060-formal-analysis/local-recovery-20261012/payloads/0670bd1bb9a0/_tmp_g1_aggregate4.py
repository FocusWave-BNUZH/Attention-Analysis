# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：核查零眨眼事件场次的机制。

用途：判断 "no_blink_events" 是来源确实无事件，还是事件存在但落在 NIR 记录窗口之外，
从而区分来源缺失与对齐过滤。本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_aggregate4_out.txt")
LINES: list[str] = []


def emit(text: str) -> None:
    """打印并缓存一行结果。"""
    print(text)
    LINES.append(text)


def main() -> None:
    events_path = Path(
        r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\RGB\11_analysis_tables\tables\rgb_blink_candidate_events.csv"
    )
    events = pd.read_csv(events_path)
    emit(f"event_columns={list(events.columns)}")

    g1 = Path(
        r"D:\Project\.codex-worktrees\Attention-Analysis-1.16-g0-20260912\outputs\nir_pupil_blink_audit_g1_20260912_160556"
    )
    sync = pd.read_csv(g1 / "rgb_nir_sync_audit.csv")
    zero = sync[sync["sync_status"] == "no_blink_events"]

    time_cols = [c for c in events.columns if "unix_ms" in c or "start" in c or "end" in c]
    emit(f"event_time_columns={time_cols}")

    for _, row in zero.iterrows():
        session_id = row["session_id"]
        session_events = events[events["session_id"].astype(str).eq(str(session_id))]
        if session_events.empty:
            emit(f"{session_id}: no rows in RGB blink event table (source-side absence)")
            continue
        start_col = next((c for c in ("start_unix_ms", "start_ms") if c in session_events.columns), None)
        if start_col is None:
            emit(f"{session_id}: rows={len(session_events)} but no start time column")
            continue
        starts = pd.to_numeric(session_events[start_col], errors="coerce")
        inside = int(((starts >= row["nir_time_min_ms"]) & (starts <= row["nir_time_max_ms"])).sum())
        emit(
            f"{session_id}: rgb_rows={len(session_events)} "
            f"rgb_start_range=[{starts.min():.0f},{starts.max():.0f}] "
            f"nir_range=[{row['nir_time_min_ms']:.0f},{row['nir_time_max_ms']:.0f}] "
            f"events_inside_nir_window={inside}"
        )

    emit("")
    emit("===== 对照：有事件的场次 sub-032 =====")
    row = sync[sync["session_id"] == "sub-032"].iloc[0]
    session_events = events[events["session_id"].astype(str).eq("sub-032")]
    starts = pd.to_numeric(session_events["start_unix_ms"], errors="coerce")
    inside = int(((starts >= row["nir_time_min_ms"]) & (starts <= row["nir_time_max_ms"])).sum())
    emit(
        f"sub-032 rgb_rows={len(session_events)} rgb_range=[{starts.min():.0f},{starts.max():.0f}] "
        f"nir_range=[{row['nir_time_min_ms']:.0f},{row['nir_time_max_ms']:.0f}] inside={inside} "
        f"reported_blink_event_n={row['blink_event_n']}"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
