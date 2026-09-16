#!/usr/bin/env python3
"""把草稿 + 素材 + 导入说明打成一个可发送的包（文件夹 + zip）。

    python scripts/package_draft.py --resolved work/resolved.json --draft-name "项目名" --out ~/Desktop

素材清单从 resolved.json 推导，不去解析剪映保存后的 draft_info.json（那已经是密文）。
打包前请确认剪映已关闭，否则会复制到写了一半的目录。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import zipfile

MAC_DRAFTS = pathlib.Path.home() / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
WIN_DRAFTS = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro/User Data/Projects/com.lveditor.draft"

NOTE = """{title}（剪映工程）导入说明
========================================

这个包里有三样东西：
  草稿文件夹/     剪映草稿本体
  素材/           草稿用到的全部素材（画面 + 配音 + 配乐）
  导入说明.txt     本文件

导入步骤
----------------------------------------
1. 把「{draft_name}」整个文件夹放进本机剪映的草稿目录：
   · macOS：~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/
   · Windows：C:\\Users\\<用户名>\\AppData\\Local\\JianyingPro\\User Data\\Projects\\com.lveditor.draft\\
2. 打开剪映，首页「本地草稿」里会出现这个工程，点开。
3. 提示素材丢失时点「重新链接」，选中解压出来的「素材」文件夹。
   剪映按文件名自动匹配，一次就能全部找回（每个素材文件名唯一）。
4. 链接完成后即可正常预览、剪辑、导出。

工程信息
----------------------------------------
· 画幅 {width}x{height} · {fps}fps · 总时长 {duration}s
· 轨道：{tracks}
· 画面里的变速已按原样写入片段，请不要重新变速，否则会和配音、字幕错位。
· 文案为甲方原稿，未改写。
"""


def drafts_root() -> pathlib.Path:
    override = os.environ.get("JY_PROJECTS_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return MAC_DRAFTS if platform.system() == "Darwin" else WIN_DRAFTS


def jianying_running() -> bool:
    if platform.system() == "Darwin":
        return subprocess.run(["pgrep", "-f", "VideoFusion-macOS.app/Contents/MacOS"], capture_output=True).returncode == 0
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq JianyingPro.exe"], capture_output=True, text=True)
    return "JianyingPro.exe" in (result.stdout or "")


def collect_media(resolved: dict, project_dir: pathlib.Path) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for shot in resolved["shots"]:
        paths.append(pathlib.Path(shot["path"]))
    if resolved.get("voice", {}).get("mode", "tts") == "tts":
        for beat in resolved["beats"]:
            voice_file = beat.get("file")
            paths.append(
                pathlib.Path(voice_file) if voice_file else project_dir / "work" / "vo" / f"vo_{beat['id']}.wav"
            )
    music = resolved.get("music")
    if music:
        music_path = pathlib.Path(music["path"]).expanduser()
        paths.append(music_path if music_path.is_absolute() else project_dir / music_path)
    seen, unique = set(), []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="打包剪映工程")
    parser.add_argument("--resolved", default="work/resolved.json")
    parser.add_argument("--draft-name", required=True)
    parser.add_argument("--out", default=str(pathlib.Path.home() / "Desktop"))
    parser.add_argument("--zip-name", default=None)
    args = parser.parse_args()

    resolved_path = pathlib.Path(args.resolved).expanduser().resolve()
    resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
    project_dir = resolved_path.parent.parent

    if jianying_running():
        print("⚠ 剪映正在运行：请先退出剪映再打包，否则可能复制到写了一半的草稿目录")

    source = drafts_root() / args.draft_name
    if not source.is_dir():
        raise SystemExit(f"找不到草稿：{source}")

    media = collect_media(resolved, project_dir)
    missing = [path for path in media if not path.exists()]
    if missing:
        raise SystemExit("以下素材不存在：\n" + "\n".join(str(path) for path in missing))

    out_dir = pathlib.Path(args.out).expanduser().resolve() / f"{args.draft_name}_发送版"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "素材").mkdir(parents=True)
    shutil.copytree(source, out_dir / args.draft_name)
    for path in media:
        shutil.copy2(path, out_dir / "素材" / path.name)

    width, height = (1080, 1920) if resolved.get("canvas") == "portrait" else (1920, 1080)
    style = resolved.get("style", {})
    tracks = " · ".join(filter(None, [
        style.get("video_track", "画面"),
        style.get("voice_track", "配音") if resolved.get("voice", {}).get("mode", "tts") == "tts" else None,
        style.get("music_track", "BGM") if resolved.get("music") else None,
        style.get("subtitle_track", "字幕"),
        style.get("headline_track", "标题"),
        "图卡",
    ]))
    (out_dir / "导入说明.txt").write_text(
        NOTE.format(
            title=resolved.get("title", "剪映工程"),
            draft_name=args.draft_name,
            width=width, height=height,
            fps=resolved.get("fps", 30),
            duration=resolved.get("duration"),
            tracks=tracks,
        ),
        encoding="utf-8",
    )

    archive = out_dir.with_suffix(".zip")
    archive.unlink(missing_ok=True)
    if args.zip_name:
        archive = pathlib.Path(args.zip_name).expanduser().resolve()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                handle.write(path, path.relative_to(out_dir))

    total = sum(path.stat().st_size for path in media)
    print(f"素材 {len(media)} 个 / {total / 1e6:.1f} MB")
    print(f"发送文件夹：{out_dir}")
    print(f"压缩包：{archive}  {archive.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
