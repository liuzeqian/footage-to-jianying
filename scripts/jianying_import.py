#!/usr/bin/env python3
"""把刚生成的草稿"导入"到剪映：校验 + 唤起剪映。

    python scripts/jianying_import.py --draft-name "项目名"          # 校验 + 唤起剪映
    python scripts/jianying_import.py --check                        # 只看状态，不动剪映
    python scripts/jianying_import.py --draft-name "项目名" --quit-first   # 先优雅退出剪映再启动

剪映的「草稿目录」就是它的导入目录——草稿写进去就已经在列表里了，这一步做的是：
确认草稿完整、必要时让剪映重新读取、然后把剪映唤到前台。真正点开草稿由人完成（或由具备
computer-use 能力的 agent 在剪映窗口里点列表第一项）。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import subprocess
import sys
import time

MAC_APP = pathlib.Path("/Applications/VideoFusion-macOS.app")
MAC_DRAFTS = pathlib.Path.home() / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
WIN_DRAFTS = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro/User Data/Projects/com.lveditor.draft"


def drafts_root() -> pathlib.Path:
    override = os.environ.get("JY_PROJECTS_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return MAC_DRAFTS if platform.system() == "Darwin" else WIN_DRAFTS


def app_running() -> bool:
    if platform.system() == "Darwin":
        result = subprocess.run(["pgrep", "-f", "VideoFusion-macOS.app/Contents/MacOS"], capture_output=True)
        return result.returncode == 0
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq JianyingPro.exe"], capture_output=True, text=True)
    return "JianyingPro.exe" in (result.stdout or "")


def quit_app() -> None:
    if platform.system() == "Darwin":
        subprocess.run(["osascript", "-e", 'quit app "VideoFusion-macOS"'], capture_output=True)
    else:
        subprocess.run(["taskkill", "/IM", "JianyingPro.exe"], capture_output=True)
    for _ in range(16):
        if not app_running():
            return
        time.sleep(0.5)


def launch_app() -> None:
    if platform.system() == "Darwin":
        if not MAC_APP.exists():
            raise SystemExit("没有找到剪映：/Applications/VideoFusion-macOS.app")
        subprocess.run(["open", "-a", str(MAC_APP)], check=True)
    else:
        subprocess.run(["cmd", "/c", "start", "", "JianyingPro"], check=False)


def inspect(draft_name: str | None) -> tuple[pathlib.Path | None, list[str]]:
    problems: list[str] = []
    root = drafts_root()
    if not root.is_dir():
        problems.append(f"找不到剪映草稿目录：{root}")
        return None, problems
    if not draft_name:
        return None, problems
    draft_dir = root / draft_name
    if not draft_dir.is_dir():
        problems.append(f"找不到草稿：{draft_dir}")
        return draft_dir, problems
    if not (draft_dir / "draft_info.json").exists():
        problems.append("草稿里没有 draft_info.json")
    if (draft_dir / ".locked").exists():
        problems.append("草稿目录里有 .locked（上次剪映被强制退出留下的锁文件），建议移到别处再打开")
    return draft_dir, problems


def main() -> int:
    parser = argparse.ArgumentParser(description="把草稿导入/唤起剪映")
    parser.add_argument("--draft-name")
    parser.add_argument("--check", action="store_true", help="只报告状态")
    parser.add_argument("--quit-first", action="store_true", help="先优雅退出剪映再启动")
    parser.add_argument("--no-open", action="store_true", help="只校验，不唤起剪映")
    args = parser.parse_args()

    running = app_running()
    draft_dir, problems = inspect(args.draft_name)

    print(f"剪映草稿目录：{drafts_root()}")
    if draft_dir:
        print(f"草稿：{draft_dir}")
    print(f"剪映运行中：{'是' if running else '否'}")
    for problem in problems:
        print(f"  ⚠ {problem}")

    if args.check or args.no_open:
        return 1 if [p for p in problems if "找不到草稿" in p] else 0

    if problems and any("找不到草稿" in p for p in problems):
        raise SystemExit("草稿不存在，先跑 build_jianying_draft.py")

    if running and args.quit_first:
        print("· 优雅退出剪映，让它重新读取草稿目录")
        quit_app()
        running = app_running()

    if running:
        print("· 剪映已在运行：新草稿会在回到首页时出现在「本地草稿」列表里")
    else:
        print("· 启动剪映")
        launch_app()
        time.sleep(12)

    print(
        "\n✓ 已就绪。草稿在剪映首页「本地草稿」的第一项（按修改时间排序）。\n"
        "  如果要把成片导出来，在剪映里点右上角「导出」。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
