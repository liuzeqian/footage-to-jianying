# plan.json 格式

一个项目一份 `plan.json`，是画面、配音、字幕、图卡共同的唯一真源。
完整可跑的最小示例在 [../assets/plan.example.json](../assets/plan.example.json)。

```jsonc
{
  "meta": {
    "title": "项目名",
    "canvas": "portrait",        // portrait = 1080x1920，landscape = 1920x1080
    "fps": 30,
    "media_dir": "footage"       // 相对 plan.json 的素材目录，或绝对路径
  },

  "voice": {
    "mode": "tts",               // tts | none
    "provider": "openai",
    "model": "gpt-4o-mini-tts",
    "voice": "onyx",             // alloy / echo / fable / onyx / nova / shimmer
    "instructions": "用专业、沉稳、有信念感的中文旁白语气朗读，语速中等偏快，咬字清晰。",
    "lead_in": 0.55,             // 第一句之前留白
    "outro_tail": 3.4            // 最后一句之后留白（落版时间）
  },

  "music": {
    "path": "assets/bgm/track.wav",
    "volume": 0.22
  },

  "beats": [
    { "id": "b01", "text": "你有没有注意到一个现象：……", "gap_after": 0.2 }
  ],

  "sections": [
    {
      "key": "s1",
      "beats": ["b01", "b02"],       // 这一段覆盖哪几句；段落窗口由首句起点决定
      "label": "01",                 // 左上角栏目标签，可省
      "label_text": "现象",
      "headline": "白牌换了一轮又一轮", // 段落主标题，可省（省略则该段不显示标题）
      "shots": [
        {
          "clip": "A_plant.mov",     // media_dir 里的文件名
          "in": 0.2, "out": 1.8,     // 源素材入出点（秒），窗口长度决定该镜头的权重
          "framing": "fill",         // fill = 铺满画幅；matte = 背景模糊 + 原比例画面带（仅竖屏有意义）
          "move": "in",              // in = 缓慢推近，out = 缓慢拉远
          "note": "直播间举瓶",       // 只给自己看的分镜备注
          "crop": "50% 44%"          // 仅 fill 用，object-position / 取景偏置，可省
        }
      ]
    }
  ],

  "subtitles": {
    "b01": [                       // 每句一到多"页"字幕
      ["你有没有注意到一个现象："],
      ["抖音美妆TOP20里，"],
      ["白牌换了一轮又一轮，", "大部分撑不过一年。"]
    ]
  },

  "keywords": { "b01": ["撑不过一年"] },   // 字幕里高亮的词，可省

  "cards": [
    {
      "id": "steps",               // 用于生成文字轨名：<id>1、<id>2 …
      "section": "s3",             // 显示到该段结束
      "rows": [
        { "beat": "b06", "text": "01  爆款冲量" },
        { "beat": "b07", "text": "02  品质滑坡" }
      ]
    }
  ],

  "endcard": {
    "section": "s6",
    "lines": [
      { "beat": "b18", "text": "白牌不是做不大", "role": "headline" },
      { "beat": "b19", "text": "是大部分白牌的供应链\n撑不起做大的野心", "role": "body" }
    ],
    "brand": { "text": "柏俐臣", "sub": "整条链的确定性", "delay": 1.6 }
  },

  "style": {
    "subtitle_size": 7.0,          // 剪映字号（1080 宽画布下 7.0 ≈ 58px）
    "headline_size": 9.5,
    "card_size": 5.0,
    "move_zoom": 0.07,             // move=in/out 的推拉幅度，1.0 → 1.0+move_zoom
    "subtitle_track": "字幕",
    "headline_track": "标题",
    "voice_track": "配音",
    "music_track": "BGM",
    "video_track": "画面",
    "endcard_track": "落版"
  }
}
```

## 字段要点

- `beats` 按顺序排列。每条文案是一个语义单元（一句话或一个分句），**不要**把整段话塞进一条，
  否则剪辑点会没有落点。
- `gap_after` 是该句之后的停顿（秒）。句间 0.2~0.35，段落末尾 0.6~0.9，结尾可省。
- `sections` 必须覆盖全部 beats 且首尾相接；段落窗口 = 本段首句起点 → 下段首句起点。
- `shots` 在段落内按顺序铺满，`out - in` 越长的镜头分到的时间越多，脚本自动反算变速倍率
  （源长度 ÷ 时间）。倍率落在 0.65~1.10 之外说明素材量和段落长度不匹配：加镜头或改 `in/out`。
- `move` 会落成**真正的缩放关键帧**（`EASE_IN_OUT` 缓入缓出）：`in` 从 1.0 推到 `1.0 + style.move_zoom`，
  `out` 从 `1.0 + move_zoom` 拉回 1.0，时间轴上一段两个关键帧。不想要运动就写 `move: "none"`
  或把 `style.move_zoom` 设为 0；**不写 `move` 的镜头保持静止**（不会凭空长出推镜）。
- `subtitles` 的每一页最多两行；每行控制在 12 个汉字以内（竖屏）或一行放完（横屏）。
- `cards` 的行是**累加**显示的，所以每行一个文字轨；`section` 决定它们显示到什么时候消失。
- 画幅只由 `meta.canvas` 决定。改画幅时字幕分页、图卡位置由脚本按画布换算，不用手改。
