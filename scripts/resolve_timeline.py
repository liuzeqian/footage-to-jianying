#!/usr/bin/env python3
"""把 plan.json + 配音时长解析成绝对时间轴。

    python scripts/resolve_timeline.py plan.json --timings work/vo/timings.json --out work/resolved.json

输出里每一段画面、每一条字幕、每一张图卡都有绝对起止时间，是落剪映草稿的唯一输入。
段落内的镜头按「源长度 ÷ 段落长度」自动反算变速倍率，段落边界严格落在该段第一句的起点。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

RATE_SOFT_MIN = 0.62
RATE_SOFT_MAX = 1.15


def load(path: str) -> dict:
    return json.loads(pathlib.Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def beat_timeline(plan: dict, timings: dict, plan_dir: pathlib.Path) -> tuple[list[dict], float]:
    items = {item["id"]: item for item in timings["beats"]}
    voice = plan.get("voice", {})
    lead_in = float(voice.get("lead_in", 0.55))
    outro_tail = float(voice.get("outro_tail", 3.4))

    beats, cursor = [], lead_in
    for beat in plan["beats"]:
        item = items.get(beat["id"])
        if item is None:
            raise SystemExit(f"timings.json 里没有 {beat['id']} 的时长")
        seconds = item["duration"]
        voice_file = item.get("file")
        if voice_file:
            voice_path = pathlib.Path(voice_file).expanduser()
            voice_file = str(voice_path if voice_path.is_absolute() else (plan_dir / voice_path).resolve())
        beats.append({
            "id": beat["id"],
            "text": beat["text"],
            "file": voice_file,
            "start": round(cursor, 3),
            "end": round(cursor + seconds, 3),
        })
        cursor += seconds + float(beat.get("gap_after", 0.3))
    total = round(beats[-1]["end"] + outro_tail, 3)
    return beats, total


def section_windows(plan: dict, beats: list[dict], total: float) -> dict[str, tuple[float, float]]:
    by_id = {beat["id"]: beat for beat in beats}
    starts = [by_id[section["beats"][0]]["start"] for section in plan["sections"]]
    windows: dict[str, tuple[float, float]] = {}
    for index, section in enumerate(plan["sections"]):
        start = 0.0 if index == 0 else starts[index]
        end = starts[index + 1] if index + 1 < len(plan["sections"]) else total
        windows[section["key"]] = (round(start, 3), round(end, 3))
    return windows


def build_shots(plan: dict, windows: dict[str, tuple[float, float]], media_dir: pathlib.Path) -> list[dict]:
    shots: list[dict] = []
    for section in plan["sections"]:
        key = section["key"]
        start, end = windows[key]
        span = end - start
        entries = section.get("shots", [])
        if not entries:
            raise SystemExit(f"段落 {key} 没有任何镜头")
        source_total = sum(float(item["out"]) - float(item["in"]) for item in entries)
        if source_total <= 0:
            raise SystemExit(f"段落 {key} 的镜头窗口长度不合法")
        scale = span / source_total
        cursor = start
        for index, item in enumerate(entries):
            source_in, source_out = float(item["in"]), float(item["out"])
            last = index == len(entries) - 1
            duration = round(end - cursor, 3) if last else round((source_out - source_in) * scale, 3)
            shots.append({
                "id": f"{key}_{index + 1:02d}",
                "section": key,
                "clip": item["clip"],
                "path": str((media_dir / item["clip"]).resolve()),
                "src_in": round(source_in, 3),
                "src_out": round(source_out, 3),
                "start": round(cursor, 3),
                "duration": duration,
                "rate": round(1 / scale, 4),
                "framing": item.get("framing", "fill"),
                # 不写 move 就是不做运动；写了 in/out 才会在草稿里落成缩放关键帧
                "move": item.get("move"),
                "crop": item.get("crop"),
                "note": item.get("note", ""),
            })
            cursor += duration
    return shots


def build_cues(plan: dict, beats: list[dict]) -> list[dict]:
    subtitles = plan.get("subtitles", {})
    keywords = plan.get("keywords", {})
    cues: list[dict] = []
    for beat in beats:
        pages = subtitles.get(beat["id"])
        if not pages:
            continue
        span = beat["end"] - beat["start"]
        weights = [max(sum(len(line) for line in page), 6) for page in pages]
        total_weight = sum(weights)
        cursor = beat["start"]
        for index, page in enumerate(pages):
            duration = span * weights[index] / total_weight
            cues.append({
                "id": f"{beat['id']}_{index + 1}",
                "beat": beat["id"],
                "lines": page,
                "text": "".join(page),
                "highlight": keywords.get(beat["id"], []),
                "start": round(cursor, 3),
                "duration": round(duration, 3),
            })
            cursor += duration
    return cues


def build_cards(plan: dict, beats: list[dict], windows: dict[str, tuple[float, float]]) -> list[dict]:
    by_id = {beat["id"]: beat for beat in beats}
    rows: list[dict] = []
    for card in plan.get("cards", []):
        end = windows[card["section"]][1]
        for index, row in enumerate(card.get("rows", [])):
            start = by_id[row["beat"]]["start"]
            rows.append({
                "id": f"{card['id']}_{index + 1}",
                "track": f"{card['id']}{index + 1}",
                "text": row["text"],
                "row": index,
                "start": round(start, 3),
                "duration": round(end - start, 3),
            })
    return rows


def build_endcard(plan: dict, beats: list[dict], windows: dict[str, tuple[float, float]], total: float) -> dict | None:
    endcard = plan.get("endcard")
    if not endcard:
        return None
    by_id = {beat["id"]: beat for beat in beats}
    end = windows[endcard["section"]][1]
    lines = []
    for index, line in enumerate(endcard.get("lines", [])):
        start = by_id[line["beat"]]["start"]
        lines.append({
            "id": f"end_{index + 1}",
            "text": line["text"],
            "role": line.get("role", "body"),
            "start": round(start, 3),
            "duration": round(end - start, 3),
            "track": f"落版{index + 1}",
        })
    brand = endcard.get("brand")
    if brand:
        last = beats[-1]["start"] + float(brand.get("delay", 1.6))
        lines.append({
            "id": "end_brand",
            "text": f"{brand['text']}  ·  {brand.get('sub', '')}".strip(),
            "role": "brand",
            "start": round(last, 3),
            "duration": round(max(end - last, 1.0), 3),
            "track": "落版尾",
        })
    return {"section": endcard["section"], "start": windows[endcard["section"]][0], "end": end, "lines": lines}


def build_headlines(plan: dict, windows: dict[str, tuple[float, float]]) -> list[dict]:
    rows = []
    for section in plan["sections"]:
        start, end = windows[section["key"]]
        if section.get("headline"):
            rows.append({
                "section": section["key"],
                "kind": "headline",
                "text": section["headline"],
                "start": start,
                "duration": round(end - start, 3),
            })
        if section.get("label"):
            rows.append({
                "section": section["key"],
                "kind": "label",
                "text": f"{section['label']}  {section.get('label_text', '')}".strip(),
                "start": start,
                "duration": round(end - start, 3),
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="解析绝对时间轴")
    parser.add_argument("plan")
    parser.add_argument("--timings", default="work/vo/timings.json")
    parser.add_argument("--out", default="work/resolved.json")
    args = parser.parse_args()

    plan_path = pathlib.Path(args.plan).expanduser().resolve()
    plan = load(str(plan_path))
    timings = load(args.timings)

    media_dir = pathlib.Path(plan["meta"].get("media_dir", "footage")).expanduser()
    if not media_dir.is_absolute():
        media_dir = (plan_path.parent / media_dir).resolve()

    beats, total = beat_timeline(plan, timings, plan_path.parent)
    windows = section_windows(plan, beats, total)
    shots = build_shots(plan, windows, media_dir)
    cues = build_cues(plan, beats)

    resolved = {
        "title": plan["meta"].get("title", "未命名"),
        "canvas": plan["meta"].get("canvas", "portrait"),
        "fps": plan["meta"].get("fps", 30),
        "media_dir": str(media_dir),
        "duration": total,
        "voice": plan.get("voice", {}),
        "music": plan.get("music"),
        "style": plan.get("style", {}),
        "beats": beats,
        "sections": [
            {
                "key": section["key"],
                "start": windows[section["key"]][0],
                "end": windows[section["key"]][1],
                "label": section.get("label"),
                "label_text": section.get("label_text"),
                "headline": section.get("headline"),
            }
            for section in plan["sections"]
        ],
        "shots": shots,
        "cues": cues,
        "cards": build_cards(plan, beats, windows),
        "endcard": build_endcard(plan, beats, windows, total),
        "headlines": build_headlines(plan, windows),
    }

    out_path = pathlib.Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"总时长 {total}s · 画面 {len(shots)} 段 · 字幕 {len(cues)} 条 · 图卡 {len(resolved['cards'])} 条")
    for section in resolved["sections"]:
        section_shots = [shot for shot in shots if shot["section"] == section["key"]]
        rates = [shot["rate"] for shot in section_shots]
        flag = ""
        if rates and (min(rates) < RATE_SOFT_MIN or max(rates) > RATE_SOFT_MAX):
            flag = "  ⚠ 变速倍率越界：加镜头或调整窗口长度"
        print(
            f"  {section['key']:>3}  {section['start']:7.2f} → {section['end']:7.2f}"
            f"  ({section['end'] - section['start']:6.2f}s)  镜头 {len(section_shots):2d}"
            f"  倍率 {min(rates):.2f}–{max(rates):.2f}{flag}"
        )
    print(f"\n✓ {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
