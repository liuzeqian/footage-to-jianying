#!/usr/bin/env python3
"""把刚生成的草稿"导入"到剪映：校验 + 唤起剪映 + 打开草稿。

    python scripts/jianying_import.py --draft-name "项目名"          # 校验 + 唤起剪映
    python scripts/jianying_import.py --draft-name "项目名" --open   # 再尝试直接打开并确认打开成功
    python scripts/jianying_import.py --check                        # 只看状态，不动剪映
    python scripts/jianying_import.py --draft-name "项目名" --quit-first   # 先优雅退出剪映再启动

剪映的「草稿目录」就是它的导入目录——草稿写进去就已经在列表里了，这一步做的是：
确认草稿完整、必要时让剪映重新读取、然后把剪映唤到前台、打开这条草稿。

打开草稿怎么判断：剪映打开一条草稿时会把草稿目录重写成自己的格式（多出 `Timelines/`、
`Resources/`，`draft_info.json` 变成密文），所以这里用「草稿目录的时间戳有没有变化」当指纹。
`--open` 只是尽力而为（剪映的命令行参数在 11.5 上实测不一定会直接进编辑器），
拿不到信号时会打印手动打开的指路，交由人/agent 用 UI 点开并截图确认。
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


def quit_app(timeout: float = 30.0) -> bool:
    """优雅退出剪映，返回是否确认已退出。

    剪映退出要 5~15 秒（有工程打开时更久），而且第一次发退出请求偶尔会被忽略，
    所以这里发两次、并且必须等到进程真的没了才算成功——不然调用方会以为草稿目录
    已经被重新读取，实际拿到的是旧缓存。
    """
    if not app_running():
        return True
    if platform.system() == "Darwin":
        for attempt in range(2):
            subprocess.run(["osascript", "-e", 'quit app "VideoFusion-macOS"'], capture_output=True)
            deadline = time.time() + timeout / 2
            while time.time() < deadline:
                if not app_running():
                    return True
                time.sleep(0.5)
            if attempt == 0:
                print("· 第一次退出请求没生效，再试一次")
    else:
        subprocess.run(["taskkill", "/IM", "JianyingPro.exe"], capture_output=True)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not app_running():
                return True
            time.sleep(0.5)
    return not app_running()


def launch_app(draft_dir: pathlib.Path | None = None) -> None:
    if platform.system() == "Darwin":
        if not MAC_APP.exists():
            raise SystemExit("没有找到剪映：/Applications/VideoFusion-macOS.app")
        if draft_dir is None:
            subprocess.run(["open", "-a", str(MAC_APP)], check=True)
        else:
            # 剪映认 --draft_path / --draft_from / --draft_type 这组参数（二进制里有对应的
            # 格式串），但 11.5 实测不保证直接进编辑器，所以只当"尽力而为"：
            # 真正确认打开与否由 wait_for_open() 看草稿目录有没有被重写。
            subprocess.run(
                ["open", "-a", str(MAC_APP), "--args",
                 f"--draft_path={draft_dir}", "--draft_from=local", "--draft_type=local"],
                check=False,
            )
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
        # .locked 是剪映打开草稿时写的锁：剪映在跑就是"正开着/刚开过"，
        # 剪映没在跑才是"上次没正常关闭"留下的陈旧锁。
        if app_running():
            problems.append("草稿目录里有 .locked：剪映可能正开着这条草稿（也可能是上次没正常关闭留下的）")
        else:
            problems.append("草稿目录里有 .locked，且剪映没在运行：这是上次没正常关闭留下的陈旧锁，建议移走再打开")
    return draft_dir, problems


def draft_stamp(draft_dir: pathlib.Path) -> float:
    """草稿目录里最新的修改时间，用来判断剪映有没有动过这条草稿。"""
    latest = 0.0
    for entry in draft_dir.iterdir():
        try:
            latest = max(latest, entry.stat().st_mtime)
        except OSError:
            continue
    return latest


def wait_for_open(draft_dir: pathlib.Path, before: float, timeout: float) -> bool:
    """等剪映把这条草稿重写一遍（= 真的打开了），超时就放弃。"""
    deadline = time.time() + timeout
    started = time.time()
    live = sys.stdout.isatty()
    while time.time() < deadline:
        time.sleep(1.5)
        if live:
            print(f"\r· 等待剪映打开草稿… {int(time.time() - started)}s", end="", flush=True)
        if draft_stamp(draft_dir) > before:
            if live:
                print()
            return True
    if live:
        print()
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="把草稿导入/唤起剪映")
    parser.add_argument("--draft-name")
    parser.add_argument("--check", action="store_true", help="只报告状态")
    parser.add_argument("--quit-first", action="store_true", help="先优雅退出剪映再启动")
    parser.add_argument("--no-open", action="store_true", help="只校验，不唤起剪映")
    parser.add_argument("--open", action="store_true", help="唤起后尝试直接打开这条草稿并确认")
    parser.add_argument("--wait", type=float, default=45.0, help="等待打开的最长秒数（默认 45）")
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
        if not quit_app():
            print("⚠ 剪映没有自动退出（可能有未保存弹窗，或正在导出）。")
            print("  请手动退出剪映（⌘Q）后重跑本命令；这一步做不干净，后面读到的可能是旧缓存或半截草稿。")
            return 2
        running = app_running()

    want_open = bool(args.open and draft_dir)
    stamp_before = draft_stamp(draft_dir) if want_open else 0.0

    if running:
        print("· 剪映已在运行：新草稿会在回到首页时出现在「本地草稿」列表里")
    else:
        print("· 启动剪映" + ("并尝试直接打开这条草稿" if want_open else ""))
        launch_app(draft_dir if want_open else None)
        time.sleep(12)

    if want_open:
        opened = wait_for_open(draft_dir, stamp_before, args.wait)  # type: ignore[arg-type]
        name = draft_dir.name  # type: ignore[union-attr]
        if opened:
            print(f"✓ 剪映已经打开这条草稿：{name}")
            print("  （有 UI 能力时再看一眼窗口并截图确认：画面上应该能看到成片的画面、字幕和图卡）")
        else:
            print(f"⚠ 没等到剪映打开这条草稿，它可能停在首页。手动打开：")
            print(f"  剪映首页 →「本地草稿」→ 点开「{name}」（通常是第一项，按修改时间排序）")
            print("  或由具备 computer-use 能力的 agent 在剪映窗口里点开并截图确认。")
    else:
        print(
            "\n✓ 已就绪。草稿在剪映首页「本地草稿」的第一项（按修改时间排序）。\n"
            "  加上 --open 可以让脚本尝试直接打开并确认；有 UI 能力时再点开截图确认。"
        )

    print("  要把成片导出来，在剪映里点右上角「导出」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
