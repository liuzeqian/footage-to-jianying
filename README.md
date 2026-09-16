# footage-to-jianying · 素材 + 文案 → 剪映工程

**给 Codex / WorkBuddy 用的 skill：把一堆原始素材（视频/图片）加一段口播文案，自动做成可直接继续剪的剪映专业版草稿**——画面、配音、BGM、字幕、标题、图卡、落版各占一条轨，镜头变速和推拉关键帧已经写进片段里。

> English: A Codex / WorkBuddy skill that turns raw footage plus a voiceover script into an editable JianYing (CapCut CN) draft — VO, BGM, subtitles, titles, cards and endcard on separate tracks, with per-shot speed ramps and push/pull keyframes baked in.

---

## 1. 它会产出什么

跑完一遍，你会得到三样东西：

| 产物 | 说明 |
| --- | --- |
| 剪映草稿 | 直接写进 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/<项目名>`，剪映首页「本地草稿」第一项就能看到 |
| `plan.json` / `resolved.json` | 编排数据，唯一真源。改节奏、换镜头、出横屏版都改这两个文件重跑，不用手工拖时间线 |
| 发送包（可选） | 草稿 + 素材 + 导入说明的 zip，别人解压就能导入 |

草稿的轨道结构（每条独立成轨，方便对方单独开关/改样式）：

```
画面   ← 18 段镜头，每段带变速倍率 + 推近/拉远关键帧
配音   ← 逐句 TTS，裁静音 + 响度归一
BGM    ← 一条配乐（音量、淡入淡出是渲染前就压好的）
字幕   ← 按句分页，一页最多两行
标题   ← 每段主标题
栏目   ← 左上角 01/02/03 标签
图卡1…图卡n ← 累加出现的清单，一行一轨
落版   ← 结尾大字（可选品牌行）
```

完整链路：

```
素材盘点(切点+抽帧) → plan.json → 逐句配音 → 解析绝对时间轴 → 落剪映草稿 → 唤起剪映 → (可选)打包
  probe_footage    你/LLM写     make_vo     resolve_timeline   build_jianying_draft  jianying_import   package_draft
```

**先配音、后剪画面**：段落长度由配音真实时长决定，镜头在段落内按「源长度 ÷ 段落长度」自动反算变速，整段自动填满、不会出现空隙。

---

## 2. 环境要求

| 项 | 要求 |
| --- | --- |
| 宿主 | Codex 或 WorkBuddy（两者 skill 规范一致，可同时装） |
| 剪映 | **专业版（国内版）11.x**，实测 11.4 可用。CapCut 国际版、手机端剪映**不行** |
| 系统 | macOS（本文命令按 macOS 写；Windows 走 `%LOCALAPPDATA%\JianyingPro\...`，未实测） |
| 其他 | `ffmpeg` / `ffprobe`、Python 3.10+ |
| 可选 | `OPENAI_API_KEY`（生成配音用；没有就把 `plan.voice.mode` 设成 `"none"`） |

---

## 3. 安装

### 3.1 一条命令

```bash
git clone <本仓库地址> ~/Desktop/skills/footage-to-jianying
cd ~/Desktop/skills/footage-to-jianying
./install.sh --venv
```

`install.sh` 会做四件事：

1. 复制到 `~/.codex/skills/footage-to-jianying`（Codex）和 `~/.workbuddy/skills/footage-to-jianying`（WorkBuddy）——哪边目录存在就装哪边；
2. 检查这两个 `skills/` 下有没有 `jianying-editor`（草稿写入依赖），没有会提示；
3. 检查 `ffmpeg` / `ffprobe` / `OPENAI_API_KEY`；
4. `--venv` 时在仓库里建 `.venv` 并装 `requests`。

常用变体：

```bash
./install.sh --codex            # 只装 Codex
./install.sh --workbuddy        # 只装 WorkBuddy
./install.sh --link             # 用软链接，改仓库即时生效（开发时用）
./install.sh --target /tmp/skills   # 装到别的 skills 目录（调试用）
```

装完**重启一下宿主应用**（Codex / WorkBuddy），新 skill 才会被扫描到。

### 3.2 手动安装（等价做法）

```bash
# Codex
mkdir -p ~/.codex/skills && cp -R . ~/.codex/skills/footage-to-jianying
# WorkBuddy
mkdir -p ~/.workbuddy/skills && cp -R . ~/.workbuddy/skills/footage-to-jianying
```

两个宿主都想用同一份代码，可以软链，改一处两边都生效：

```bash
ln -s ~/Desktop/skills/footage-to-jianying ~/.codex/skills/footage-to-jianying
ln -s ~/Desktop/skills/footage-to-jianying ~/.workbuddy/skills/footage-to-jianying
```

### 3.3 安装运行时依赖 `jianying-editor`（必须）

本仓库**不包含**写草稿的库，它复用现成的 `jianying-editor` skill（里面有 `JyWrapper` 和 vendored `pyJianYingDraft`，MIT 协议）。挑一个上游克隆过去：

```bash
# 上游 A（3.1k★，本流程实测用的就是它）
git clone https://github.com/luoluoluo22/jianying-editor-skill.git ~/.codex/skills/jianying-editor

# WorkBuddy 也要用就再来一份
git clone https://github.com/luoluoluo22/jianying-editor-skill.git ~/.workbuddy/skills/jianying-editor

# 上游 B（另一套实现，字段兼容性自行验证）
# git clone https://github.com/isYangs/jianying-editor-skill.git ~/.codex/skills/jianying-editor
```

装到别处也可以，脚本会按 `JY_EDITOR_SKILL` 环境变量找：

```bash
export JY_EDITOR_SKILL=~/projects/jianying-editor
```

查找顺序：`JY_EDITOR_SKILL` → `~/.codex/skills/jianying-editor` → `~/.workbuddy/skills/jianying-editor`。

### 3.4 自检

```bash
cd ~/Desktop/skills/footage-to-jianying
python3 scripts/jianying_import.py --check     # 剪映草稿目录 + 剪映是否在跑
python3 -c "import sys; sys.path.insert(0,'scripts'); import build_jianying_draft; print('草稿写入依赖 OK')"
```

---

## 4. 快速开始

以「桌面 `video/` 里前两条素材混剪成一条片子」为例，项目目录自己定，下面是本流程的标准布局：

```bash
mkdir -p ~/Desktop/mixcut/work && cd ~/Desktop/mixcut
```

**① 盘点素材**（拿到时长、分辨率、切点候选 + 逐镜头抽帧图）

```bash
python3 ~/Desktop/skills/footage-to-jianying/scripts/probe_footage.py work/footage --out work/footage.json
# → work/footage.json + work/contact_sheets/*.jpg（看图核对镜头，不要只看数字）
```

**② 写 `plan.json`**：从 `assets/plan.example.json` 复制，按下一节的字段表改。核心是三段：`beats`（文案切句）、`sections`（段落 + 镜头）、`subtitles`（字幕分页）。

**③ 生成配音**

```bash
python3 ~/Desktop/skills/footage-to-jianying/scripts/make_vo.py plan.json --out work/vo
# → work/vo/vo_b01.wav … + work/vo/timings.json（真实时长，决定段落长度）
```

**④ 解析时间轴**（打印每段变速倍率，倍率超界会警告）

```bash
python3 ~/Desktop/skills/footage-to-jianying/scripts/resolve_timeline.py plan.json \
  --timings work/vo/timings.json --out work/resolved.json
```

**⑤ 落剪映草稿**（写草稿时剪映必须是关闭的）

```bash
python3 ~/Desktop/skills/footage-to-jianying/scripts/jianying_import.py --check      # 确认剪映没在跑
python3 ~/Desktop/skills/footage-to-jianying/scripts/build_jianying_draft.py plan.json \
  --resolved work/resolved.json --draft-name "我的混剪"
```

**⑥ 唤起剪映并打开草稿**

```bash
python3 ~/Desktop/skills/footage-to-jianying/scripts/jianying_import.py \
  --draft-name "我的混剪" --quit-first --open
```

草稿目录就是剪映的导入目录，唤起后它会出现在首页「本地草稿」第一项。
`--open` 会让脚本带上 `--draft_path` 尽力直接打开这条草稿，并**盯草稿目录的时间戳**确认真的打开了
（剪映打开草稿会把目录重写成自己的格式：多出 `Timelines/`、`Resources/`，`draft_info.json` 变密文；
没打开过的草稿没有这些特征）。拿不到信号时它不会假装成功，而是打印手动打开的指路。

> 这一步的验收标准是**你在剪映里看得见这条片子**：有 computer-use 能力的 agent 会自己在首页点开
> 这条草稿并截图确认；没有 UI 能力时至少要给你草稿绝对路径 + "首页本地草稿第一项"的明确指路。

**⑦ 需要发给别人时打包**（同样要在剪映关闭时做）

```bash
python3 ~/Desktop/skills/footage-to-jianying/scripts/package_draft.py \
  --resolved work/resolved.json --draft-name "我的混剪" --out ~/Desktop
```

出竖屏 / 横屏两个版本？只改 `plan.meta.canvas`（`portrait` / `landscape`），重跑第 ④⑤ 步，镜头和配音都不用动。

---

## 5. 在 Codex / WorkBuddy 里直接说人话

装好并重启后，两个宿主的用法一样——skill 的 `description` 命中就会自动加载：

> 「用 footage-to-jianying，把 `~/Desktop/video` 里前两个素材混剪一条 30 秒的片子」
>
> 「素材在 `~/Desktop/raw`，文案在 `script.txt`，出一版竖屏剪映工程」
>
> 「这条工程节奏太慢，把第 2 段剪紧一点，重跑草稿」

它们的差别只在 skill 目录：Codex 读 `~/.codex/skills/`，WorkBuddy 读 `~/.workbuddy/skills/`；本仓库两边都能装，命令行用法完全一致。

---

## 6. `plan.json` 字段速查

| 字段 | 作用 |
| --- | --- |
| `meta.canvas` | `portrait`(1080×1920) / `landscape`(1920×1080) |
| `meta.media_dir` | 素材目录（相对 plan.json 或绝对路径） |
| `voice.mode` | `tts` / `none`；`voice.voice` 选音色，`lead_in`/`outro_tail` 是头尾留白 |
| `music.path` / `music.volume` | BGM（音量建议 0.2~0.3；脚本会原样用一个音频轨） |
| `beats[]` | 文案切句，一条一个语义单元；`gap_after` 是句后停顿（句间 0.2~0.35，段末 0.6~0.9） |
| `sections[]` | 段落：`beats` 覆盖哪些句、`label`/`headline`、`shots` 镜头表 |
| `shots[].in` / `.out` | 源素材入出点（秒）。**窗口越长，分到的画面时间越多**，脚本自动反算变速 |
| `shots[].move` | `in` 缓慢推近 / `out` 缓慢拉远 → 落成真缩放关键帧（缓入缓出）；不写 = 静止 |
| `shots[].framing` / `.crop` | 取景意图（`fill` 铺满 / `matte` 画面带）与偏置，给人和预览用 |
| `subtitles` | 每句 1~多页字幕；竖屏一行 ≤12 汉字，一页 ≤2 行 |
| `cards[]` | 累加图卡，一行一条（**每行会自动分轨**） |
| `endcard` | 落版大字 + 可选品牌行 |
| `style.move_zoom` | 推拉幅度，默认 `0.07`（1.0 → 1.07）；不想要运动就设 0 |
| `style.*_size` / `*_track` | 字号（1080 宽画布下 7.0 ≈ 58px）与轨道名 |

---

## 7. 实战案例（本仓库自测的那条）

素材：两条 AI 生成的 15s 企业片（1344×768 研发/产线 + 2560×1440 仓储/交付）
产出：**29.3 秒 · 18 段画面 · 8 句旁白 · 10 条字幕 · 3 张累加图卡 · 竖屏 + 横屏两版**

- 分段：现象 → 后端（研发/品控/产能）→ 交付，段边界严格落在句首；
- 变速：三段统一 0.80×/0.83×/1.00×，全在舒适区间；
- 运动：18 段镜头每段两个缩放关键帧（`KFTypeScaleX` + `EASE_IN_OUT`），推近 10 段、拉远 8 段；
- 竖屏版先把 16:9 素材「烘焙」成 1080×1920（低分辨率素材用模糊底衬 + 原比例画面带，高清素材用 9:16 铺满裁切），再落草稿，所以没有黑边。

---

## 8. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| 写草稿报错或剪映读到旧内容 | **写草稿前必须先退出剪映**；`jianying_import.py --quit-first` 会自动退 |
| 打开草稿提示「素材丢失」 | 草稿里是绝对路径。发给别人要用 `package_draft.py` 连素材一起打包，对方用「重新链接」指到素材文件夹 |
| 剪映保存后 `draft_info.json` 变密文了 | 正常，剪映会把它重存成自己的格式；素材清单要从 plan 侧推导 |
| 打开草稿时长显示 00:00 | 剪映还没解析过，打开一次即恢复 |
| 段落提示「变速倍率越界」 | 素材量与该段长度不匹配：加镜头、改 `in/out`，或调整文案长度 |
| 图卡只看到最后一条 | 图卡必须一行一轨（本流程已按行分轨） |
| 文字上下颠倒 | 剪映 `transform_y` **向上为正**，与屏幕坐标相反 |
| 导不出 mp4 | 本流程只负责出**工程**；macOS 下剪映不支持命令行导出，打开草稿点右上角「导出」 |
| 没有 OPENAI_API_KEY | 把 `plan.voice.mode` 设为 `"none"`，只出画面 + 字幕（时长按字数估算） |
| `--open` 提示"没等到剪映打开草稿" | 剪映接受了 `--draft_path` 参数但停在首页（11.5 实测不一定直接进编辑器）。按提示在首页「本地草稿」点开那条草稿即可；agent 有 UI 能力时应当自己点开并截图 |

---

## 9. 目录结构

```
footage-to-jianying/
├─ SKILL.md              # 技能入口（宿主靠它识别；含必须守住的约束）
├─ install.sh            # 一键装到 Codex / WorkBuddy
├─ requirements.txt      # 运行时 python 依赖（requests）
├─ scripts/
│   ├─ probe_footage.py         # 素材盘点：时长/分辨率/切点/抽帧拼图
│   ├─ make_vo.py               # 逐句 TTS + 裁静音 + 响度归一
│   ├─ resolve_timeline.py      # 解析绝对时间轴、反算变速
│   ├─ build_jianying_draft.py  # 落剪映草稿（多轨 + 变速 + 关键帧）
│   ├─ jianying_import.py       # 校验草稿 + 唤起剪映
│   └─ package_draft.py         # 草稿 + 素材 + 导入说明打包
├─ references/           # plan 格式、素材分析、剪映草稿契约与排错
├─ assets/plan.example.json
└─ agents/openai.yaml
```

---

## 10. 许可与致谢

本仓库代码 MIT（见 `LICENSE`）。

运行时依赖（**未包含在本仓库内**，需自行安装，遵循各自许可）：

- [luoluoluo22/jianying-editor-skill](https://github.com/luoluoluo22/jianying-editor-skill) — 草稿写入层（MIT）
- [GuanYixuan/pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) — 剪映草稿协议库（MIT，随上面那个 skill 一起安装）

素材、文案、配乐的版权归各自权利人，本仓库不附带任何素材。
