# -*- coding: utf-8 -*-
"""
文件名：extract_rgb_examples_20260831.py
版本：v1.0
功能：从 RGB 原始视频抽帧，标注面孔眼睛关键点（EAR / 眨眼用）与体动姿势骨架（肩/肘/腕/髋等），
      无文字注释。选 1 个好（sub-114）与 1 个差（sub-084）session，各 10 帧，输出到 new_figure/RGB_examples/。
      复用 face_raw.parquet（眼睛 mesh 点）与 pose_landmarks.parquet（体动关节）。
用法：python extract_rgb_examples_20260831.py
依赖：opencv-python, numpy, pandas, pyarrow
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pyarrow  # noqa: F401  确保可读 parquet

DATA_ROOT = r"J:/Data"
RGB_PROC = r"D:/Project/厚粲杯/11_数据/04_Attention-Analysis_nvidia-cuda_RGB"
OUT_DIR = r"D:/Project/厚粲杯/11_数据/_FormalAnalysis/new_figure/RGB_examples"
N_FRAMES = 10

GOOD = "sub-114"
BAD = "sub-084"

# 眼睛 EAR 关键点（MediaPipe mesh 索引）：外眼角 33/263，内眼角 133/362，上睑 159/386，下睑 145/374
EYE_POINTS = [33, 263, 133, 362, 159, 145, 386, 374]
EYE_COLOR = (0, 200, 0)  # 绿色 (BGR)
BODY_COLOR = (0, 120, 255)  # 橙色 (BGR)
EYE_RADIUS = 3
JOINT_RADIUS = 5

# 体动姿势关节（pose_landmarks landmark_name）
BODY_JOINTS = ["nose", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
               "left_wrist", "right_wrist", "left_hip", "right_hip"]
BODY_BONES = [("nose", "left_shoulder"), ("nose", "right_shoulder"),
              ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
              ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
              ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip")]


def _load_eye_landmarks(sid):
    """读 face_raw.parquet，返回 (video_frame_position, 眼睛点 dict)。"""
    p = Path(RGB_PROC) / sid / f"{sid}_face_raw.parquet"
    if not p.exists():
        return {}
    cols = ["video_frame_position", "FaceScore"] + [f"mesh_x_{i}" for i in EYE_POINTS] + [f"mesh_y_{i}" for i in EYE_POINTS]
    df = pd.read_parquet(p, columns=[c for c in cols if c in pd.read_parquet(p, columns=None).columns])
    return df


def _load_body_landmarks(sid):
    """读 pose_landmarks.parquet，pivot 成 video_frame_position × 关节(x,y)。"""
    p = Path(RGB_PROC) / sid / f"{sid}_pose_landmarks.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "landmark_name" not in df.columns or "video_frame_position" not in df.columns:
        return pd.DataFrame()
    sub = df[df["landmark_name"].isin(BODY_JOINTS)][["video_frame_position", "landmark_name", "x", "y"]]
    wide = sub.pivot_table(index="video_frame_position", columns="landmark_name", values=["x", "y"])
    return wide


def _pick_frames(eye_df, body_df):
    """挑 N_FRAMES 帧：优先有脸且有体动的，间隔均匀。"""
    frames = set(eye_df["video_frame_position"].dropna().astype(int).tolist()) if not eye_df.empty else set()
    if not body_df.empty:
        frames &= set(body_df.index.astype(int))
    if not frames:
        frames = set(eye_df["video_frame_position"].dropna().astype(int).tolist())
    frames = sorted(frames)
    if len(frames) <= N_FRAMES:
        return frames
    idx = np.linspace(0, len(frames) - 1, N_FRAMES).astype(int)
    return [frames[i] for i in idx]


def _extract_frame(video_path, frame_idx):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def _save_img(path, img):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix or ".jpg", img)
    if ok:
        path.write_bytes(buf.tobytes())


def _annotate(frame, fidx, eye_row, body_row):
    h, w = frame.shape[:2]
    # 眼睛关键点
    if eye_row is not None:
        for i in EYE_POINTS:
            x = eye_row.get(f"mesh_x_{i}")
            y = eye_row.get(f"mesh_y_{i}")
            if x is not None and y is not None and pd.notna(x) and pd.notna(y):
                cv2.circle(frame, (int(x), int(y)), EYE_RADIUS, EYE_COLOR, -1)
    # 体动骨架（MediaPipe pose 坐标为归一化 0-1，乘图像尺寸并裁剪）
    if body_row is not None:
        joints = {}
        for j in BODY_JOINTS:
            try:
                xv = body_row.get(("x", j))
                yv = body_row.get(("y", j))
            except Exception:
                continue
            if xv is None or yv is None or pd.isna(xv) or pd.isna(yv):
                continue
            try:
                px = int(float(xv) * w)
                py = int(float(yv) * h)
            except (ValueError, TypeError):
                continue
            joints[j] = (max(0, min(w - 1, px)), max(0, min(h - 1, py)))
        for a, b in BODY_BONES:
            if a in joints and b in joints:
                cv2.line(frame, joints[a], joints[b], BODY_COLOR, 2)
        for pt in joints.values():
            cv2.circle(frame, pt, JOINT_RADIUS, BODY_COLOR, -1)
    return frame


def main():
    for sid, good in [(GOOD, True), (BAD, False)]:
        video = Path(DATA_ROOT) / f"{sid}_" / "rgb" / f"{sid}_rgb.avi"
        if not video.exists():
            print(f"跳过 {sid}: 无 RGB 视频")
            continue
        eye_df = _load_eye_landmarks(sid)
        body_df = _load_body_landmarks(sid)
        frames = _pick_frames(eye_df, body_df)
        sub = "good" if good else "bad"
        print(f"=== {sid} ({sub}) 选帧 {len(frames)} ===")
        for i, fidx in enumerate(frames[:N_FRAMES]):
            frame = _extract_frame(video, fidx)
            if frame is None:
                continue
            eye_row = eye_df[eye_df["video_frame_position"] == fidx].iloc[0].to_dict() if not eye_df.empty and not eye_df[eye_df["video_frame_position"] == fidx].empty else None
            body_row = body_df.loc[fidx] if (not body_df.empty and fidx in body_df.index) else None
            frame = _annotate(frame, fidx, eye_row, body_row)
            _save_img(Path(OUT_DIR) / f"{sid}_{sub}_{i+1:02d}_annotated.jpg", frame)
        # 同时输出一帧未标注原图作对照
    print(f"完成，输出到 {OUT_DIR}")


if __name__ == "__main__":
    main()
