"""Stage A read-only figure audit for FormalScience Behavior/Movement/Ocular.

Reads the real local FormalScience assets and writes audit CSVs plus low-volume
contact-sheet previews. It never fits a model, never writes inside FormalScience,
and never modifies any authoritative figure or table.

Usage:
    python audit_bmo_figures.py <out_dir>
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image

SCI = Path(r"D:\Project\厚粲杯\11_数据\_FormalAnalysis\FormalScience")
MODALITIES = ("Behavior", "Movement", "Ocular")

CJK = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef\u3000-\u303f]")
# Raw program identifiers exposed as visible text.
FIELDY = re.compile(
    r"[a-z][a-z0-9]*(?:__[a-z0-9]+)+"                       # ocular__rseg_hard__...
    r"|(?:body_motion|exposure_change|pose_|pupil_|hard_|soft_|analysis_|go_correct)"
    r"|(?:nir_qc_only|rgb_nir_qc|rgb_blink_only|original_nir)"
    r"|(?:q1_nominal|q2_ordinal|mnlogit|ordinal_gee|_median|_per_min|_per_sec|_rate|_ms\b)"
)
ABBR = re.compile(r"\b(GEE|CI|SD|MAD|IQR|CV|Z|OR|QC)\b")
MODEL_TERM = re.compile(r"\b(Intercept|block2|progression|slope difference|within-person|between-person)\b", re.I)

SECTION = {
    "Behavior": "5.2",
    "Movement": "5.4",
    "Ocular": "5.3",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_meta(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    dpi = None
    i = 8
    while i < len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        if kind == b"pHYs":
            x, _y, unit = struct.unpack(">IIB", data[i + 8:i + 17])
            dpi = round(x * 0.0254) if unit == 1 else None
            break
        if kind == b"IDAT":
            break
        i += 12 + length
    return {"png_px_w": width, "png_px_h": height, "png_dpi": dpi, "png_bytes": len(data)}


def svg_text(svg: Path) -> list[str]:
    raw = svg.read_text(encoding="utf-8", errors="ignore")
    nodes = re.findall(r"<text[^>]*>(.*?)</text>", raw, flags=re.S)
    out = [re.sub("<[^>]+>", "", n).strip() for n in nodes]
    return [t for t in out if t]


def svg_path_points(svg: Path) -> list[tuple[float, float]]:
    """Absolute move points from path data, used as a within-panel ink proxy."""
    raw = svg.read_text(encoding="utf-8", errors="ignore")
    pts: list[tuple[float, float]] = []
    for d in re.findall(r'\sd="([^"]+)"', raw):
        for x, y in re.findall(r"[ML]\s*(-?\d+\.?\d*)[ ,](-?\d+\.?\d*)", d):
            try:
                pts.append((float(x), float(y)))
            except ValueError:
                continue
    return pts


def cluster_ratio(points: list[tuple[float, float]]) -> float:
    """Fraction of ink points that are indistinguishably close to another point.

    A high value is a structural warning for overplotted / overlapping traces
    (for example many participant lines over a narrow band), not proof of visual
    overlap; the visual check remains authoritative.
    """
    if len(points) < 40:
        return 0.0
    grid: dict[tuple[int, int], int] = {}
    for x, y in points:
        grid[(int(x), int(y))] = grid.get((int(x), int(y)), 0) + 1
    crowded = sum(v for v in grid.values() if v > 1)
    return round(crowded / len(points), 3)


def contact_sheet(pngs: list[Path], dest: Path, cols: int = 3, thumb_w: int = 420) -> None:
    if not pngs:
        return
    thumbs = []
    for p in pngs:
        im = Image.open(p).convert("RGB")
        ratio = thumb_w / im.width
        thumbs.append((p, im.resize((thumb_w, max(1, int(im.height * ratio))))))
    rows = (len(thumbs) + cols - 1) // cols
    row_h = [max(t.height for _, t in thumbs[r * cols:(r + 1) * cols]) for r in range(rows)]
    sheet = Image.new("RGB", (cols * thumb_w, sum(row_h)), "white")
    y = 0
    for r in range(rows):
        for c, (_p, t) in enumerate(thumbs[r * cols:(r + 1) * cols]):
            sheet.paste(t, (c * thumb_w, y))
        y += row_h[r]
    sheet.save(dest, "PNG", optimize=True)


def main() -> int:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "preview").mkdir(exist_ok=True)

    repo = Path(r"D:\Project\厚粲杯\08_算法\Attention-Analysis")
    audit_rows: list[dict[str, object]] = []
    asset_rows: list[dict[str, object]] = []
    table_rows: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    checksum_rows: list[dict[str, object]] = []

    for modality in MODALITIES:
        root = SCI / modality
        fdir = root / "figures"
        pngs = sorted(p for p in fdir.rglob("*.png")) if fdir.is_dir() else []

        for p in sorted(f for f in root.rglob("*") if f.is_file()):
            rel = p.relative_to(root).as_posix()
            area = p.parent.name if p.parent != root else "-"
            asset_rows.append({
                "modality": modality, "relative_path": rel, "area": area,
                "kind": p.suffix.lstrip("."), "bytes": p.stat().st_size,
            })
            checksum_rows.append({
                "modality": modality, "relative_path": rel,
                "bytes": p.stat().st_size, "sha256": sha256(p),
            })
            if rel.startswith("tables/"):
                table_rows.append({
                    "modality": modality, "table": p.name, "bytes": p.stat().st_size,
                    "sha256": sha256(p),
                })
            if rel.startswith("manifests/"):
                manifest_rows.append({
                    "modality": modality, "manifest": p.name, "bytes": p.stat().st_size,
                    "sha256": sha256(p),
                })

        for png in pngs:
            svg = png.with_suffix(".svg")
            texts = svg_text(svg) if svg.is_file() else []
            cjk = [t for t in texts if CJK.search(t)]
            raw_fams = svg.read_text(encoding="utf-8", errors="ignore") if svg.is_file() else ""
            has_cjk_font = bool(re.search(r"(SimSun|YaHei|SimHei|CJK)", raw_fams))
            fieldy = sorted({t for t in texts if FIELDY.search(t)})
            abbr = sorted({t for t in texts if ABBR.search(t) and not CJK.search(t)})
            model_term = sorted({t for t in texts if MODEL_TERM.search(t)})
            meta = png_meta(png)
            overlap = cluster_ratio(svg_path_points(svg)) if svg.is_file() else 0.0
            audit_rows.append({
                "modality": modality,
                "section": SECTION[modality],
                "figure_id": png.stem,
                "area": png.parent.name,
                "png_path": png.relative_to(root).as_posix(),
                "svg_present": svg.is_file(),
                "png_px": f"{meta['png_px_w']}x{meta['png_px_h']}",
                "png_dpi": meta["png_dpi"],
                "rendered_text_n": len(texts),
                "cjk_text_n": len(cjk),
                "cjk_font_assigned": has_cjk_font if cjk else "n/a",
                "missing_glyph_risk": "no" if (not cjk or has_cjk_font) else "YES",
                "longest_label_chars": max((len(t) for t in texts), default=0),
                "raw_program_field_n": len(fieldy),
                "raw_program_field_sample": " | ".join(fieldy[:3])[:160],
                "english_abbrev_n": len(abbr),
                "english_abbrev_sample": " | ".join(abbr[:4])[:120],
                "model_term_n": len(model_term),
                "model_term_sample": " | ".join(model_term[:4])[:120],
                "overplot_proxy": overlap,
                "ci_visible": "yes" if any(re.search(r"[−\-]\d", t) for t in texts) else "check",
            })

        contact_sheet(pngs, out / "preview" / f"{modality}_contact_sheet.png")

    def dump(name: str, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        with (out / name).open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    dump("asset_inventory.csv", asset_rows)
    dump("real_figure_audit.csv", audit_rows)
    dump("formal_table_inventory.csv", table_rows)
    dump("manifest_inventory.csv", manifest_rows)
    dump("checksums_sha256.csv", checksum_rows)

    (out / "git_status.txt").write_text(
        subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                       capture_output=True, text=True).stdout
        + subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout
        + subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                         capture_output=True, text=True).stdout,
        encoding="utf-8",
    )
    print(json.dumps({
        "figures_audited": len(audit_rows),
        "assets": len(asset_rows),
        "tables": len(table_rows),
        "manifests": len(manifest_rows),
        "previews": [p.name for p in sorted((out / "preview").glob("*.png"))],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
