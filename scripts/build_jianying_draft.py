#!/usr/bin/env python3
"""把 resolved.json 落成剪映草稿。

    python scripts/build_jianying_draft.py plan.json --resolved work/resolved.json --draft-name "项目名"

画幅由 plan.meta.canvas 决定（portrait 1080x1920 / landscape 1920x1080）。
画面、配音、配乐、字幕、标题、图卡、落版各自独立成轨；累计显示的图卡每行一条轨。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys


def find_editor_skill() -> pathlib.Path:
    """定位剪映草稿写入库所在的那个 skill 目录。

    顺序：`JY_EDITOR_SKILL` 环境变量 → `~/.codex/skills/jianying-editor`
    → `~/.workbuddy/skills/jianying-editor`。两个宿主（Codex / WorkBuddy）装的
    skill 目录不同，所以这里不能写死路径。
    """
    candidates: list[pathlib.Path] = []
    env = os.environ.get("JY_EDITOR_SKILL")
    if env:
        candidates.append(pathlib.Path(env).expanduser())
    for home in (".codex", ".workbuddy"):
        candidates.append(pathlib.Path.home() / home / "skills" / "jianying-editor")
    for candidate in candidates:
        if (candidate / "scripts" / "jy_wrapper.py").exists():
            return candidate
    raise SystemExit(
        "找不到 jianying-editor skill（草稿写入依赖它）。请任选一种方式：\n"
        "  1) 装到 ~/.codex/skills/jianying-editor（Codex）\n"
        "  2) 装到 ~/.workbuddy/skills/jianying-editor（WorkBuddy）\n"
        "  3) 设 JY_EDITOR_SKILL=/path/to/jianying-editor\n"
        "安装方式见本仓库 README「安装运行时依赖」一节。"
    )


JY_SKILL = find_editor_skill()
sys.path.insert(0, str(JY_SKILL / "scripts"))
homebrew_bin = "/opt/homebrew/bin"
if homebrew_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = homebrew_bin + ":" + os.environ.get("PATH", "")

import jy_wrapper  # noqa: E402
from jy_wrapper import JyProject  # noqa: E402

draft = jy_wrapper.draft

CANVAS = {"portrait": (1080, 1920), "landscape": (1920, 1080)}

# transform_y 的单位是「半个画布高」，向上为正（与屏幕坐标相反）
POSITIONS = {
    "portrait": {
        "subtitle": -0.60,
        "headline": 0.65,
        "card_rows": (-0.236, -0.308, -0.380, -0.452),
        "end_lines": (-0.327, -0.465, -0.646),
    },
    "landscape": {
        "subtitle": -0.756,
        "headline": 0.556,
        "card_rows": (0.230, 0.107, -0.015, -0.137),
        "end_lines": (0.541, 0.357, 0.174),
    },
}

DEFAULT_STYLE = {
    "subtitle_size": 7.0,
    "headline_size": 9.5,
    "card_size": 5.0,
    "move_zoom": 0.07,
    "video_track": "画面",
    "voice_track": "配音",
    "music_track": "BGM",
    "subtitle_track": "字幕",
    "headline_track": "标题",
    "label_track": "栏目",
    "endcard_track": "落版",
}

# plan 里 move=in/out 的推近、拉远幅度：画面上从 1.0 变到 1.0 + move_zoom
MOVE_ZOOM = 0.07

DRAFTS_ROOT = pathlib.Path.home() / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"


def drafts_root() -> pathlib.Path:
    override = os.environ.get("JY_PROJECTS_ROOT")
    return pathlib.Path(override).expanduser() if override else DRAFTS_ROOT


class Builder:
    def __init__(self, project: JyProject, style: dict, canvas: str):
        self.project = project
        self.style = style
        self.pos = POSITIONS[canvas]
        self.cursors: dict[str, int] = {}
        self.materials: dict[str, object] = {}
        self.border = draft.TextBorder(color=(0.0, 0.0, 0.0), alpha=1.0, width=30.0)

    # ── 画面 ────────────────────────────────────────────────────────────────
    def add_shot(self, shot: dict) -> None:
        track = self.style["video_track"]
        material = self.materials.get(shot["path"])
        if material is None:
            material = draft.VideoMaterial(shot["path"])
            self.materials[shot["path"]] = material
        start = max(int(round(shot["start"] * 1_000_000)), self.cursors.get(track, 0))
        segment = draft.VideoSegment(
            material,
            draft.trange(start, int(round(shot["duration"] * 1_000_000))),
            source_timerange=draft.trange(
                int(round(shot["src_in"] * 1_000_000)),
                int(round((shot["src_out"] - shot["src_in"]) * 1_000_000)),
            ),
            speed=shot["rate"],
        )
        self.project.script.add_segment(segment, track)
        self._apply_move(segment, shot)
        # 播放器按源长度÷速度以微秒重算时长，与毫秒取整会差几百微秒，用真实结束点接续避免重叠
        self.cursors[track] = segment.target_timerange.end

    def _apply_move(self, segment, shot: dict) -> None:
        """把 plan 里的 move 落成真正的缩放关键帧（缓入缓出）。

        in = 缓慢推近，out = 缓慢拉远，其它值（含 none）不做运动。
        曲线上用库里的贝塞尔预设；库若不支持缓动参数则退回线性。
        """
        move = str(shot.get("move") or "").lower()
        if move not in ("in", "out"):
            return
        add_keyframe = getattr(segment, "add_keyframe", None)
        if add_keyframe is None:
            return
        zoom = float(self.style.get("move_zoom", MOVE_ZOOM) or 0)
        if zoom <= 0:
            return
        duration_us = int(round(float(shot["duration"]) * 1_000_000))
        if duration_us <= 0:
            return
        scale_from, scale_to = (1.0, 1.0 + zoom) if move == "in" else (1.0 + zoom, 1.0)
        easing = getattr(getattr(draft, "Keyframe", None), "EASE_IN_OUT", {}) or {}
        prop = draft.KeyframeProperty.uniform_scale
        add_keyframe(prop, 0, scale_from, **easing)
        add_keyframe(prop, duration_us, scale_to, **easing)

    # ── 音频 ────────────────────────────────────────────────────────────────
    def add_audio(self, path: str, start: float, duration: float, track: str) -> None:
        self.project.add_media_safe(str(path), start_time=start, duration=duration, track_name=track)

    # ── 文字 ────────────────────────────────────────────────────────────────
    def add_text(self, text: str, start: float, duration: float, track: str, y: float, size: float) -> None:
        start_us = max(int(round(start * 1_000_000)), self.cursors.get(track, 0))
        duration_us = max(int(round(duration * 1_000_000)), 33_333)
        self.project.add_text_simple(
            text,
            start_time=start_us,
            duration=duration_us,
            track_name=track,
            style=draft.TextStyle(size=size, bold=size >= 6.0, color=(1.0, 1.0, 1.0), align=1),
            border=self.border,
            clip_settings=draft.ClipSettings(transform_y=y),
        )
        self.cursors[track] = start_us + duration_us


def main() -> int:
    parser = argparse.ArgumentParser(description="生成剪映草稿")
    parser.add_argument("plan")
    parser.add_argument("--resolved", default="work/resolved.json")
    parser.add_argument("--draft-name", default=None)
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args()

    plan_path = pathlib.Path(args.plan).expanduser().resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    resolved = json.loads(pathlib.Path(args.resolved).expanduser().resolve().read_text(encoding="utf-8"))

    style = {**DEFAULT_STYLE, **resolved.get("style", {})}
    canvas = resolved.get("canvas", "portrait")
    if canvas not in CANVAS:
        raise SystemExit(f"未知画幅：{canvas}")
    width, height = CANVAS[canvas]
    draft_name = args.draft_name or resolved.get("title", "未命名工程")

    project = JyProject(
        draft_name,
        width=width,
        height=height,
        drafts_root=str(drafts_root()),
        overwrite=not args.no_overwrite,
    )
    project._ensure_track(draft.TrackType.video, style["video_track"])
    builder = Builder(project, style, canvas)

    for shot in resolved["shots"]:
        builder.add_shot(shot)

    voice = resolved.get("voice", {})
    if voice.get("mode", "tts") == "tts":
        missing = []
        for beat in resolved["beats"]:
            wav = pathlib.Path(beat.get("file") or (plan_path.parent / "work" / "vo" / f"vo_{beat['id']}.wav"))
            if not wav.exists():
                missing.append(str(wav))
                continue
            builder.add_audio(str(wav), beat["start"], beat["end"] - beat["start"], style["voice_track"])
        if missing:
            raise SystemExit(
                "配音文件缺失，草稿会变成没有旁白的废片，已中止：\n  "
                + "\n  ".join(missing[:6])
                + (f"\n  …共 {len(missing)} 个" if len(missing) > 6 else "")
            )

    music = resolved.get("music")
    if music:
        music_path = pathlib.Path(music["path"]).expanduser()
        if not music_path.is_absolute():
            music_path = plan_path.parent / music_path
        builder.add_audio(str(music_path), 0.0, resolved["duration"], style["music_track"])

    for cue in resolved["cues"]:
        builder.add_text(
            "\n".join(cue["lines"]), cue["start"], cue["duration"],
            style["subtitle_track"], builder.pos["subtitle"], style["subtitle_size"],
        )

    for row in resolved["headlines"]:
        if row["kind"] == "headline":
            builder.add_text(row["text"], row["start"], row["duration"],
                             style["headline_track"], builder.pos["headline"], style["headline_size"])
        else:
            builder.add_text(row["text"], row["start"], row["duration"],
                             style["label_track"], builder.pos["headline"] + 0.16, style["card_size"])

    for card in resolved["cards"]:
        rows = builder.pos["card_rows"]
        y = rows[min(card["row"], len(rows) - 1)]
        builder.add_text(card["text"], card["start"], card["duration"], card["track"], y, style["card_size"])

    endcard = resolved.get("endcard")
    if endcard:
        for index, line in enumerate(endcard["lines"]):
            if line["role"] == "brand":
                y = builder.pos["end_lines"][-1] - 0.18
                size = style["card_size"]
            elif line["role"] == "headline":
                y = builder.pos["end_lines"][0]
                size = style["headline_size"]
            else:
                y = builder.pos["end_lines"][min(index, len(builder.pos["end_lines"]) - 1)]
                size = style["headline_size"]
            builder.add_text(line["text"], line["start"], line["duration"], line["track"], y, size)

    result = project.save()
    print("RESULT:", result)
    print(
        f"画幅 {width}x{height} · 画面 {len(resolved['shots'])} 段 · "
        f"字幕 {len(resolved['cues'])} 条 · 标题 {len([r for r in resolved['headlines'] if r['kind'] == 'headline'])} 条 · "
        f"图卡 {len(resolved['cards'])} 条 · 时长 {resolved['duration']}s"
    )
    print(f"草稿目录：{drafts_root() / draft_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
