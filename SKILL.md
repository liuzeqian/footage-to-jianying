---
name: footage-to-jianying
description: 把一堆原始素材（视频/图片）加一段口播文案，做成可直接继续剪辑的剪映专业版工程（草稿），并打包成能发给别人导入的文件。当用户给出素材文件夹 + 文案，要求"剪成一条片子""出一版剪映工程""发给别人导入剪映"时使用。不适合：只烧字幕、只剪单个片段、CapCut 国际版或手机端剪映、纯动画无实拍素材。
metadata:
  short-description: 素材 + 文案 → 剪映工程
  version: "1.2.0"
---

# 素材 + 文案 → 剪映工程

## 交付什么

1. 一个剪映专业版草稿，落在 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/<项目名>`，
   画面/配音/字幕/图卡都在各自的轨道上，客户团队可以直接接着剪。
2. **最后自动把剪映唤起、让这条草稿出现在首页列表里**（第 6 步，默认必做，不是可选收尾）。
3. 需要发给别人时，再出一个发送包（草稿 + 素材 + 导入说明，zip）。

顺带产出的是编排数据（`plan.json` / `resolved.json`）：它是唯一真源，之后要改节奏、换镜头、
出横屏版，都改这两个文件重跑脚本，而不是去手工拖时间线。

注意第 1 步的草稿是**直接写进剪映草稿目录**的，所以"导入"本身不需要额外操作——第 6 步做的是
校验草稿完整、让剪映重新读取并把它唤到前台。写草稿时剪映必须是关闭状态。

## 环境前提

- 剪映**专业版（国内版）**，11.x 实测可用；CapCut 国际版与手机端不行。
- **运行时要有一个 `jianying-editor` skill**（草稿写入依赖它的 `JyWrapper` / `pyJianYingDraft`）。
  脚本按 `JY_EDITOR_SKILL` 环境变量 → `~/.codex/skills/jianying-editor` → `~/.workbuddy/skills/jianying-editor`
  的顺序找，所以 Codex 和 WorkBuddy 装哪一个都行，装两个也行。
- `ffmpeg` / `ffprobe`。
- Python 依赖装在**独立 venv** 里（`requests`，配音用），别往系统 python 装。
  本仓库的 `install.sh` 会顺手建好；手工建法：

```bash
python3 -m venv <本 skill 目录>/.venv && <本 skill 目录>/.venv/bin/python -m pip install requests
```

- 配音用 OpenAI TTS，需要 `OPENAI_API_KEY`（可选 `OPENAI_BASE_URL`）。没有就设 `voice.mode = "none"`，
  只出画面 + 字幕的工程。

## 链路

按顺序走，每步的产物都是下一步的输入：

1. **盘点素材** — `python scripts/probe_footage.py <素材目录> --out work/footage.json`
   得到每条素材的时长/分辨率/切点和逐镜头抽帧图。**必须看图核对镜头内容**，别只信切点数字。
   做法与注意点见 [references/footage-analysis.md](references/footage-analysis.md)。
2. **写 plan.json** — 文案切句、分段落、挑镜头、写字幕分页。字段定义见
   [references/plan-format.md](references/plan-format.md)；
   从 [assets/plan.example.json](assets/plan.example.json) 起步。
3. **生成配音** — `python scripts/make_vo.py plan.json --out work/vo`
   逐句合成、裁静音、响度归一，产出 `work/vo/vo_<beat>.wav` 和 `timings.json`。
4. **解析时间轴** — `python scripts/resolve_timeline.py plan.json --timings work/vo/timings.json --out work/resolved.json`
   把段落、镜头、字幕、图卡的绝对时间全部算出来，并打印每段的变速倍率供检查。
5. **落草稿** —
   `python scripts/build_jianying_draft.py plan.json --resolved work/resolved.json --draft-name "<项目名>"`
   写草稿前确认剪映已退出：`python scripts/jianying_import.py --check`
6. **导入剪映 + 打开草稿（必须做的一步）** —
   `python scripts/jianying_import.py --draft-name "<项目名>" --quit-first --open`
   剪映的草稿目录就是它的导入目录，所以校验完直接唤起剪映即可：草稿会出现在首页「本地草稿」
   第一项（按修改时间排序）。`--quit-first` 让剪映重新读取目录，避免它用旧缓存；
   `--open` 会让脚本带上 `--draft_path` 尽力直接打开这条草稿，并**盯草稿目录的时间戳**确认
   "真的打开了"——剪映打开一条草稿会把目录重写成自己的格式（多出 `Timelines/`、`Resources/`，
   `draft_info.json` 变密文），没打开过的草稿不具备这些特征。
   **这一步要的是"看得见"，不是"已导入"**：脚本没拿到打开信号时，必须接着做——
   有 computer-use 能力就自己在剪映首页点开这条草稿并截图确认（画面上要能看到自己的画面/字幕/图卡），
   没有 UI 能力就把草稿绝对路径 + "首页本地草稿第一项"明确讲清楚。
   **禁止只丢一句"已导入，去首页第一项打开"就收工。**
7. **打包给对方（需要时才做）** —
   `python scripts/package_draft.py --resolved work/resolved.json --draft-name "<项目名>" --out ~/Desktop`

要出竖屏/横屏两个版本时，只改 `plan.meta.canvas`，重跑第 4、5 步即可；镜头和配音不用动。

## 必须守住的约束

这些是实际踩出来的，违反了不会报错，只会出废片：

- **先配音，后剪画面。** 配音的真实时长决定段落长度和剪辑点；不要先按"感觉"排画面再配旁白。
- **段落边界落在句子起点。** 每个段落（section）的第一个镜头从该段第一句的起点开始，
  段落长度 = 到下一段第一句的起点。镜头在段落内部按"源长度 ÷ 段落长度"反算变速，整段自动填满。
- **剪映同一轨道不能重叠。** 相邻片段用上一段的**真实结束点**接续（脚本已处理）；
  播放器重算时长是微秒级，编排表里是毫秒取整，差几百微秒就会判重叠。
- **累计出现的图卡要各自分轨。** 四步循环这类"一行一行加上去"的图卡，每条文案一个文字轨，
  否则后一条会覆盖前一条。
- **剪映的 `transform_y` 向上为正。** 想放在画面上方用正值，下方用负值——和常规屏幕坐标相反。
- **`move` 现在是真关键帧。** `in`/`out` 会写成缩放关键帧（缓入缓出，幅度由 `style.move_zoom` 控制），
  不写 `move` 的镜头保持静止。
- **交付前必须真的打开过那条草稿。** 判据是脚本拿到"草稿目录被剪映重写"的信号，或者自己点开并
  截图确认过；草稿损坏、轨道重叠、素材丢失只有打开才看得见，`--open` 没信号不算完成。
- **素材是按绝对路径引用的。** 草稿文件夹单独发给别人必然"素材丢失"，必须连素材一起打包含说明。
- **打包要在剪映关闭时做。** 剪映打开草稿后会把它重新保存成加密格式、还写 `.locked` 和缓存，
  这时复制会拿到不一致的快照。
- **剪映重新保存＝工程变成它自己的格式。** 这是正常的；不要在剪映保存后再去解析 `draft_info.json`，
  它已经是密文。素材清单要从 plan 侧推导。
- **镜头切点会漂移。** 自动场景检测的时间点经常和真实切点差 1 秒以上（尤其 AI 生成的素材），
  取镜头时用**镜头中点附近**的窗口，并以抽帧图为准核对。
- **文案一字不改。** 客户给的文案原样上屏；画面里不出现文案之外的数字或结论。

## 排错

草稿相关的报错、字段含义、版本兼容问题见 [references/jianying-contract.md](references/jianying-contract.md)。

另外提醒：`hyperframes` 的 Studio 预览服务（如果开着）可能回写工程文件、插入分组 id，
与本技能无关；本技能的产物是剪映草稿，不依赖 HyperFrames。
