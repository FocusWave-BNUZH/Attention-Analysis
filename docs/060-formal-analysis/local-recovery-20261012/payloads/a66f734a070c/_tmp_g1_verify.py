# -*- coding: utf-8 -*-
"""临时核验脚本（不进入正式分析链路）：NIR G1 全量测量审计的清单与结构核验。

用途：核验 G1 输出是否覆盖当前兼容 NIR 队列、失败表是否为空、候选参数状态是否仍为
未冻结，并汇总同步/可用性/buffer/bin/QC 配对等关键审计表的总体结果。
本文件为一次性核查脚本，核验完成后删除。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

OUT = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis\work\_tmp_g1_verify_out.txt")
LINES: list[str] = []


def emit(text: str) -> None:
    """同时打印并缓存一行结果，避免控制台编码问题导致输出丢失。"""
    print(text)
    LINES.append(text)


def section(title: str) -> None:
    emit("")
    emit(f"===== {title} =====")


def main() -> None:
    root = Path(sys.argv[1])
    emit(f"root={root}")
    emit(f"root_exists={root.exists()}")
    if not root.exists():
        OUT.write_text("\n".join(LINES), encoding="utf-8")
        return

    section("输出文件清单")
    for path in sorted(root.rglob("*")):
        if path.is_file():
            emit(f"{path.relative_to(root)} | {path.stat().st_size} bytes")

    section("manifest")
    for name in ("run_manifest.json", "manifest.json", "audit_manifest.json", "execution_manifest.json"):
        path = root / name
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            emit(f"{name}_keys={list(data.keys())}")
            emit(f"{name}={json.dumps(data, ensure_ascii=False, default=str)[:6000]}")

    section("CSV 概要")
    for path in sorted(root.rglob("*.csv")):
        try:
            frame = pd.read_csv(path)
        except Exception as error:  # noqa: BLE001 - 核验脚本需要报告而不是中断
            emit(f"{path.relative_to(root)} READ_ERROR {type(error).__name__}: {error}")
            continue
        emit(f"{path.relative_to(root)} rows={len(frame)} cols={len(frame.columns)}")
        emit(f"  columns={list(frame.columns)}")
        for key in ("session_id", "subject_id", "participant_group_id"):
            if key in frame.columns:
                emit(f"  unique_{key}={frame[key].nunique()}")
        for key in (
            "formal_parameter_status",
            "parameter_status",
            "status",
            "source_status",
            "buffer_seconds",
            "bin_seconds",
            "bin_name",
            "cleaning_track",
            "eye_source",
        ):
            if key in frame.columns:
                counts = frame[key].value_counts(dropna=False).head(12).to_dict()
                emit(f"  value_counts_{key}={json.dumps({str(k): int(v) for k, v in counts.items()}, ensure_ascii=False)}")
        emit("  head=" + json.dumps(frame.head(3).to_dict("records"), ensure_ascii=False, default=str)[:2500])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()
