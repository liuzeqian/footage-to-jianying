#!/usr/bin/env python3
"""逐句生成配音并测量时长。

    python scripts/make_vo.py plan.json --out work/vo

产出 work/vo/vo_<beat>.wav（裁掉首尾静音 + 响度归一到 -16 LUFS）和 work/vo/timings.json。
timings.json 是下一步解析时间轴的输入；`voice.mode = "none"` 时按字数估算时长，不出音频。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

CHARS_PER_SECOND = 4.8  # 中文旁白经验值，仅在没有真实配音时用于估算


def duration_of(path: pathlib.Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return round(float(result.stdout.strip()), 3)


def polish(source: pathlib.Path, target: pathlib.Path) -> None:
    filters = (
        "silenceremove=start_periods=1:start_silence=0.06:start_threshold=-45dB:detection=peak,"
        "areverse,"
        "silenceremove=start_periods=1:start_silence=0.10:start_threshold=-45dB:detection=peak,"
        "areverse,"
        "loudnorm=I=-16:TP=-1.5:LRA=9"
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-af", filters,
         "-ar", "48000", "-ac", "2", str(target)],
        check=True,
    )


def synthesize(text: str, voice: dict, target: pathlib.Path) -> None:
    import requests  # 延迟导入：mode=none 时不需要 requests

    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("缺少 OPENAI_API_KEY；或把 plan.voice.mode 设为 \"none\"")

    payload = {
        "model": voice.get("model", "gpt-4o-mini-tts"),
        "voice": voice.get("voice", "onyx"),
        "input": text,
        "response_format": "mp3",
    }
    if voice.get("instructions"):
        payload["instructions"] = voice["instructions"]
    if voice.get("speed"):
        payload["speed"] = float(voice["speed"])

    last_error = ""
    for attempt in range(4):
        try:
            response = requests.post(
                f"{base}/audio/speech",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                data=json.dumps(payload).encode("utf-8"),
                timeout=180,
            )
            if response.status_code == 200 and len(response.content) > 2000:
                target.write_bytes(response.content)
                return
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as error:  # noqa: BLE001
            last_error = repr(error)
        time.sleep(2 + attempt * 3)
    raise SystemExit(f"TTS 失败：{last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="逐句生成配音")
    parser.add_argument("plan")
    parser.add_argument("--out", default="work/vo")
    parser.add_argument("--force", action="store_true", help="忽略已有音频重新合成")
    args = parser.parse_args()

    plan_path = pathlib.Path(args.plan).expanduser().resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    out_dir = pathlib.Path(args.out).expanduser().resolve()
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    voice = plan.get("voice", {})
    mode = voice.get("mode", "tts")
    beats = plan["beats"]
    timings = []
    total = 0.0

    for beat in beats:
        beat_id, text = beat["id"], beat["text"]
        wav = out_dir / f"vo_{beat_id}.wav"
        if mode == "tts":
            raw = raw_dir / f"{beat_id}.mp3"
            if args.force or not wav.exists():
                if args.force or not raw.exists():
                    synthesize(text, voice, raw)
                polish(raw, wav)
            seconds = duration_of(wav)
        else:
            seconds = round(max(len(text) / CHARS_PER_SECOND, 1.0), 3)
        total += seconds
        if mode == "tts":
            try:
                stored = str(wav.relative_to(plan_path.parent))
            except ValueError:
                stored = str(wav)
        else:
            stored = None
        timings.append({"id": beat_id, "text": text, "file": stored, "duration": seconds})
        print(f"{beat_id}  {seconds:6.3f}s  {len(text):3d}字  {text[:24]}")

    payload = {"mode": mode, "voice": voice.get("voice"), "total": round(total, 3), "beats": timings}
    (out_dir / "timings.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ {len(beats)} 句 / 共 {total:.2f}s → {out_dir / 'timings.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
