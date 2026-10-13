# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：复现同步审计对零事件场次的过滤路径。

用途：判定 no_blink_events 是来源无事件、会话名不匹配，还是审计读取了另一份事件表。
本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from attention_pipeline.nir_formal_analysis.pupil_blink_measurement import _normalize_blink_events
from attention_pipeline.nir_formal_analysis.pupil_blink_measurement_runner import _session_events

OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_aggregate5_out.txt")
LINES: list[str] = []


def emit(text: str) -> None:
    """打印并缓存一行结果。"""
    print(text)
    LINES.append(text)


def main() -> None:
    path = Path(
        r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\RGB\11_analysis_tables\tables\rgb_blink_candidate_events.csv"
    )
    blinks = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    emit(f"loaded_rows={len(blinks)} sessions={blinks['session_id'].nunique()}")
    emit(f"session_id_dtype={blinks['session_id'].dtype}")
    emit(f"session_id_repr_sample={[repr(v) for v in blinks['session_id'].head(3).tolist()]}")

    for session_id in ("sub-031", "sub-037", "sub-038", "sub-057", "sub-059", "sub-065", "sub-104", "sub-123", "sub-126", "sub-134", "sub-167", "sub-032"):
        events = _session_events(blinks, session_id)
        normalized = _normalize_blink_events(events, [session_id]) if not events.empty else events
        emit(f"{session_id}: _session_events_n={len(events)} normalized_n={len(normalized)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
