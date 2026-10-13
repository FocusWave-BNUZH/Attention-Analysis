# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：定位 sub-041 损坏产物并核对 NIR 队列覆盖。

用途：确认失败场次是否可用替代来源、量化 4 个零眨眼事件场次与缺列预测子的来源，
并给出融合队列可直接使用的覆盖事实。本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_aggregate3_out.txt")
LINES: list[str] = []


def emit(text: str) -> None:
    """打印并缓存一行结果。"""
    print(text)
    LINES.append(text)


def main() -> None:
    rgb_root = Path(r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\RGB\10_analysis_ready")
    events = Path(r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\RGB\11_analysis_tables\tables\rgb_blink_candidate_events.csv")

    emit("===== A. RGB analysis-ready 目录中哪些 sub-041 产物不可读 =====")
    for session_dir in sorted(rgb_root.iterdir()):
        if not session_dir.is_dir():
            continue
        for parquet in sorted(session_dir.glob("*.parquet")):
            try:
                meta = pq.ParquetFile(parquet).metadata
                _ = meta.num_rows
            except Exception as error:  # noqa: BLE001 - 核验脚本需要枚举失败
                emit(f"UNREADABLE {parquet} size={parquet.stat().st_size} {type(error).__name__}: {error}")

    emit("")
    emit("===== B. 全部场次 parquet 可读性普查 =====")
    bad: list[str] = []
    total = 0
    for parquet in sorted(rgb_root.rglob("*.parquet")):
        total += 1
        try:
            pq.ParquetFile(parquet).metadata
        except Exception as error:  # noqa: BLE001
            bad.append(f"{parquet} | {type(error).__name__}: {error}")
    emit(f"parquet_total={total} unreadable={len(bad)}")
    for entry in bad:
        emit(f"  {entry}")

    emit("")
    emit("===== C. RGB 眨眼事件表覆盖 =====")
    blink = pd.read_csv(events)
    emit(f"rows={len(blink)} sessions={blink['session_id'].nunique()}")
    counts = blink.groupby("session_id").size()
    emit(f"per_session_events: {counts.describe().round(2).to_dict()}")
    emit(f"sessions_with_events={counts.index.tolist()}")

    emit("")
    emit("===== D. 零眨眼事件场次的 RGB 帧轴可用性 =====")
    g1 = Path(r"D:\Project\.codex-worktrees\Attention-Analysis-1.16-g0-20260912\outputs\nir_pupil_blink_audit_g1_20260912_160556")
    sync = pd.read_csv(g1 / "rgb_nir_sync_audit.csv")
    zero = sync[sync["sync_status"] == "no_blink_events"]
    emit(f"no_blink_events_sessions={zero['session_id'].tolist()}")
    emit(
        "zero_event_frame_axis="
        + json.dumps(
            zero[
                [
                    "session_id",
                    "blink_event_n",
                    "rgb_frame_axis_available",
                    "frame_nearest_residual_abs_median_ms",
                    "sync_evidence_level",
                    "rgb_blink_source_available",
                ]
            ].to_dict("records"),
            ensure_ascii=False,
        )
    )
    zero_ids = set(zero["session_id"])
    emit(f"zero_event_sessions_present_in_rgb_blink_events={sorted(zero_ids & set(blink['session_id'].unique()))}")

    emit("")
    emit("===== E. 队列覆盖 =====")
    manifest = Path(r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\mapping\nir_analysis_ready_source_manifest.json")
    source_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    requested = [entry["session_id"] for entry in source_manifest["sessions"]]
    emitted = set(sync["session_id"])
    emit(f"manifest_session_n={len(requested)}")
    emit(f"requested_not_emitted={sorted(set(requested) - emitted)}")
    emit(f"emitted_not_requested={sorted(emitted - set(requested))}")
    behavior_probe = pd.read_csv(
        r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\Behavior\formal_v3\probe_primary_30s.csv",
        usecols=["session_id", "participant_group_id"],
    )
    behavior_sessions = set(behavior_probe["session_id"].astype(str))
    emit(f"behavior_session_n={len(behavior_sessions)}")
    emit(f"nir_requested_missing_from_behavior={sorted(set(requested) - behavior_sessions)}")
    emit(f"behavior_missing_from_nir_requested={sorted(behavior_sessions - set(requested))}")
    candidates = pd.read_csv(g1 / "probe_measurement_candidates.csv", usecols=["session_id", "participant_group_id"])
    emit(f"g1_candidate_sessions={candidates['session_id'].nunique()} groups={candidates['participant_group_id'].nunique()}")
    trajectories = pd.read_csv(
        g1 / "probe_fixed_bin_trajectories.csv", usecols=["session_id", "participant_group_id", "probe_event_id"]
    )
    emit(f"g1_trajectory_sessions={trajectories['session_id'].nunique()} groups={trajectories['participant_group_id'].nunique()}")
    emit(f"g1_probe_event_n={trajectories['probe_event_id'].nunique()}")
    behavior_probe_events = behavior_probe.merge(
        pd.read_csv(
            r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\Behavior\formal_v3\probe_primary_30s.csv",
            usecols=["session_id", "block_id", "probe_event_id"],
        ),
        on="session_id",
    )
    emit(f"behavior_probe_event_n={behavior_probe_events['probe_event_id'].nunique()}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
