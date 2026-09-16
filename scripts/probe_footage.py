#!/usr/bin/env python3
"""盘点素材目录：元信息、切点、抽帧拼图。

    python scripts/probe_footage.py <素材目录> --out work/footage.json [--scene 0.25]

输出 work/footage.json + work/contact_sheets/*.jpg。抽帧图是判断镜头内容的唯一可靠依据，
自动切点只作参考。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command[:4])} … failed:\n{result.stderr[-800:]}")
    return result.stdout


def probe_media(path: pathlib.Path) -> dict:
    raw = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
        "-of", "json", str(path),
    ])
    data = json.loads(raw)
    info: dict = {
        "file": path.name,
        "path": str(path),
        "duration": round(float(data.get("format", {}).get("duration", 0) or 0), 3),
        "has_audio": False,
        "width": None,
        "height": None,
        "fps": None,
        "kind": "video" if path.suffix.lower() in VIDEO_EXT else "image",
    }
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            info["has_audio"] = True
            info["audio"] = f"{stream.get('codec_name')} {stream.get('channels')}ch {stream.get('sample_rate')}Hz"
        if stream.get("codec_type") == "video" and info["width"] is None:
            info["width"] = stream.get("width")
            info["height"] = stream.get("height")
            rate = stream.get("r_frame_rate") or "0/1"
            numerator, _, denominator = rate.partition("/")
            try:
                info["fps"] = round(float(numerator) / float(denominator or 1), 3)
            except (ValueError, ZeroDivisionError):
                info["fps"] = None
    return info


def cut_points(path: pathlib.Path, threshold: float) -> list[float]:
    """自动场景切点（仅作参考，必须以抽帧为准）。"""
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(path),
            "-filter:v", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    return [round(float(value), 3) for value in re.findall(r"pts_time:([0-9.]+)", result.stderr)]


def extract(path: pathlib.Path, timestamps: list[float], size: int, out_dir: pathlib.Path, prefix: str) -> list[pathlib.Path]:
    frames: list[pathlib.Path] = []
    for index, timestamp in enumerate(timestamps):
        target = out_dir / f"{prefix}_{index:03d}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y",
                "-ss", f"{max(timestamp, 0):.3f}", "-i", str(path),
                "-vf", f"scale={size}:-1", "-frames:v", "1", str(target),
            ],
            check=True,
        )
        frames.append(target)
    return frames


def tile(frames: list[pathlib.Path], columns: int, target: pathlib.Path, label: str) -> bool:
    if not frames:
        return False
    rows = (len(frames) + columns - 1) // columns
    with tempfile.TemporaryDirectory() as scratch:
        scratch_dir = pathlib.Path(scratch)
        for index, frame in enumerate(frames):
            (scratch_dir / f"f{index:03d}.jpg").write_bytes(frame.read_bytes())
        empty = rows * columns - len(frames)
        for index in range(len(frames), len(frames) + empty):
            (scratch_dir / f"f{index:03d}.jpg").write_bytes(frames[-1].read_bytes())
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y",
                "-i", str(scratch_dir / "f%03d.jpg"),
                "-filter_complex", f"tile={columns}x{rows}:padding=6:color=0x1a1a1a",
                "-frames:v", "1", str(target),
            ],
            check=True,
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="盘点素材目录")
    parser.add_argument("media_dir")
    parser.add_argument("--out", default="work/footage.json")
    parser.add_argument("--scene", type=float, default=0.25, help="场景检测阈值")
    parser.add_argument("--frame-size", type=int, default=420)
    parser.add_argument("--shots-per-sheet", type=int, default=12)
    args = parser.parse_args()

    media_dir = pathlib.Path(args.media_dir).expanduser().resolve()
    if not media_dir.is_dir():
        raise SystemExit(f"素材目录不存在：{media_dir}")

    out_path = pathlib.Path(args.out).expanduser().resolve()
    sheet_dir = out_path.parent / "contact_sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        path for path in media_dir.iterdir()
        if path.suffix.lower() in VIDEO_EXT | IMAGE_EXT and not path.name.startswith(".")
    )
    if not files:
        raise SystemExit(f"{media_dir} 里没有找到视频/图片素材")

    report = {"media_dir": str(media_dir), "clips": []}
    for path in files:
        info = probe_media(path)
        print(f"· {path.name}  {info['duration']}s  {info['width']}x{info['height']}  fps={info['fps']}")

        if info["kind"] == "video" and info["duration"] > 0:
            info["cuts"] = cut_points(path, args.scene)
            print(f"    cut 候选 {len(info['cuts'])} 个：{info['cuts'][:12]}")

            # 均匀采样：先看清整条素材的镜头结构
            count = min(args.shots_per_sheet, max(int(info["duration"] // 1.25), 4))
            step = info["duration"] / (count + 0.5)
            uniform = [round(step * (index + 0.5), 3) for index in range(count)]
            frames = extract(path, uniform, args.frame_size, sheet_dir, f"{path.stem}_u")
            sheet = sheet_dir / f"{path.stem}.jpg"
            if tile(frames, 4, sheet, "uniform"):
                info["contact_sheet"] = str(sheet)
                info["sample_times"] = uniform

            # 按切点取每个镜头中点：用于核对每个镜头的实际画面
            bounds = [0.0, *[value for value in info["cuts"] if value < info["duration"] - 0.2], info["duration"]]
            mids = [round((bounds[i] + bounds[i + 1]) / 2, 3) for i in range(len(bounds) - 1)]
            cut_frames = extract(path, mids[:24], args.frame_size, sheet_dir, f"{path.stem}_c")
            cut_sheet = sheet_dir / f"{path.stem}_cuts.jpg"
            if tile(cut_frames, 4, cut_sheet, "cuts"):
                info["cut_sheet"] = str(cut_sheet)
                info["shot_midpoints"] = mids[:24]

            for frame in frames + cut_frames:
                frame.unlink(missing_ok=True)

        report["clips"].append(info)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ {len(report['clips'])} 条素材 → {out_path}")
    print(f"✓ 抽帧拼图 → {sheet_dir}（先看这些图，再决定镜头窗口）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
