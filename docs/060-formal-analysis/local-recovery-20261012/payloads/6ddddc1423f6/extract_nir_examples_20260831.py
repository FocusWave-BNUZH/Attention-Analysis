# -*- coding: utf-8 -*-
"""
文件名：extract_nir_examples_20260831.py
版本：v1.0
功能：按 QC 挑 1 个质量好（sub-114）与 1 个质量差（sub-084）的 NIR session，各截 10 帧示例图。
      每帧输出 3 张：① 原图（从 J:\\Data 原始 avi 按 frame_idx 抽帧）；② YOLO 选择区域示意图（复用 overlays/*.jpg）；
      ③ RITNet 分割结果图（复用 *_qc/ 下 _labels.png 与 _overlay.png）。输出到 new_figure/NIR_examples/。
用法：python extract_nir_examples_20260831.py
依赖：opencv-python, numpy, pandas, pyarrow（如需读 parquet）
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

FORMAL_NIR = r"D:/Project/厚粲杯/11_数据/01_Attention-Analysis_nvidia-cuda_formal_NIR"
DATA_ROOT = r"J:/Data"
OUT_DIR = r"D:/Project/厚粲杯/11_数据/_FormalAnalysis/new_figure/NIR_examples"

# 质量好的 session（QC primary_valid_fraction 最高）与质量差的 session（最低）
GOOD = "sub-114"
BAD = "sub-084"
N_FRAMES = 10

# 质量问题 reason 关键词（用于挑"差"帧）
BAD_REASONS = ["roi_clipped", "ritnet_missing", "normalization_invalid", "ocular_fragmented"]


def _session_dir(sid):
    for d in Path(FORMAL_NIR).glob(f"{sid}_formal*"):
        return d
    return None


def _find_overlay(session_dir, phase, phase_segment, frame_idx):
    """在 overlays/ 下定位 yolo 示意图。"""
    ov_dir = session_dir / "overlays"
    if not ov_dir.is_dir():
        return None
    # 命名格式 <phase>_s<seg>_f<frame_idx>.jpg；frame_idx 为 8 位前导零
    try:
        fid_str = f"{int(frame_idx):08d}"
    except (ValueError, TypeError):
        fid_str = str(frame_idx)
    candidates = list(ov_dir.glob(f"*f{fid_str}*.jpg"))
    if candidates:
        return candidates[0]
    candidates = list(ov_dir.glob(f"*{phase}*s{phase_segment}*f{fid_str}*.jpg"))
    return candidates[0] if candidates else None


def _extract_frame(video_path, frame_idx):
    """从原始 avi 按 frame_idx 解码一帧。"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    return frame


def _save_img(path, img):
    """保存图像（中文路径用 imencode+write_bytes，避免 cv2.imwrite 静默失败）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix or ".jpg"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        path.write_bytes(buf.tobytes())


def _select_frames(session_dir, sid, good):
    """从 qc_index 按质量挑 N_FRAMES 帧。"""
    idx = list(session_dir.glob("*_qc_index.csv"))
    if not idx:
        return []
    df = pd.read_csv(idx[0])
    if good:
        # 好帧：reason 为纯 anchor（无质量问题）
        frame = df[df["reason"].astype(str).eq("anchor")]
    else:
        # 差帧：reason 含任一质量问题关键词
        mask = df["reason"].astype(str).apply(lambda r: any(k in r for k in BAD_REASONS))
        frame = df[mask]
    if frame.empty:
        frame = df  # 兜底：全部
    return frame.head(N_FRAMES).to_dict("records")


def main():
    for sid, good in [(GOOD, True), (BAD, False)]:
        sd = _session_dir(sid)
        if sd is None:
            print(f"跳过 {sid}: 无 session 目录")
            continue
        video = Path(DATA_ROOT) / f"{sid}_" / "nir" / f"{sid}_nir.avi"
        qc_dir = next((d for d in sd.iterdir() if d.name.endswith("_qc")), None)
        frames = _select_frames(sd, sid, good)
        sub = "good" if good else "bad"
        print(f"=== {sid} ({sub}) 选帧 {len(frames)} ===")
        for i, f in enumerate(frames[:N_FRAMES]):
            fidx = f["frame_idx"]
            phase, seg = f.get("phase", "block1"), f.get("phase_segment", "s1")
            # ① 原图
            raw = _extract_frame(video, fidx)
            if raw is None:
                continue
            fid_str = f"{fidx:08d}" if isinstance(fidx, (int, np.integer)) else str(fidx)
            _save_img(Path(OUT_DIR) / f"{sid}_{sub}_{i+1:02d}_raw.jpg", raw)
            # ② YOLO 示意图（overlays）
            ov = _find_overlay(sd, phase, seg, fidx)
            if ov and ov.exists():
                ov_img = cv2.imdecode(np.fromfile(str(ov), dtype=np.uint8), cv2.IMREAD_COLOR)
                if ov_img is not None:
                    _save_img(Path(OUT_DIR) / f"{sid}_{sub}_{i+1:02d}_yolo.jpg", ov_img)
            # ③ RITNet 结果图（labels / overlay）
            labels = f.get("labels_file")
            overlay = f.get("overlay_file")
            for tag, fp in [("ritnet_labels", labels), ("ritnet_overlay", overlay)]:
                if isinstance(fp, str) and fp.strip():
                    full = Path(sd) / fp  # qc_index 文件路径为相对 session 目录
                    if not full.exists():
                        continue
                    im = cv2.imdecode(np.fromfile(str(full), dtype=np.uint8), cv2.IMREAD_COLOR)
                    if im is not None:
                        _save_img(Path(OUT_DIR) / f"{sid}_{sub}_{i+1:02d}_{tag}.jpg", im)
    print(f"完成，输出到 {OUT_DIR}")


if __name__ == "__main__":
    main()
