# podcast-use

以對話驅動的 podcast / spoken-word 剪輯 skill，適用於 Claude Code 與 Codex。

[English README](README.md)

授權： [MIT](LICENSE)

**先剪輯，後包裝。**

## 相關專案

如果你對這類結合內容、思考、自我理解的工具有興趣，也可以看看 [AnatoMee](https://anatomee.app/)。

`podcast-use` 偏音訊剪輯與發佈 workflow；`AnatoMee` 更偏向自我探索與理解自己。

## 這個 skill 可以做什麼

- 用 Groq Whisper 轉錄（含 word timestamps，可快取）
- 打包成適合閱讀與剪輯的 `takes_packed.md`
- 分析靜音、贅詞候選、可能的重講片段
- 讓 LLM 提出分級剪輯方案（安全 / 可選 / 有風險）
- 產出可驗證的 EDL：`edl.draft.json` → `edl.approved.json`
- 用 ffmpeg 渲 preview / final，並套用 spoken-word 聲音處理
- 可選：字幕、YouTube 靜態影片、reels、show notes 等發佈素材

## 設計原則

1. **先鎖定模式** — cleanup / shorten / clip / takes / review-only / publish
2. **先批准再 final render** — draft → preview → approve → final
3. **不切字中** — 對齊 word timestamps
4. **不做假 diarization** — 多人內容只依語意剪，不把講者標示當真值
5. **包裝是第二階段** — 封面 / reels / 文案在剪輯鎖定後再做

## 目前限制

- 這條 Groq Whisper workflow **不提供真正的 speaker diarization**
- 雙人 / 多人仍可轉錄與內容剪輯
- 不要把 `Speaker A / B` 當可發佈的正式 attribution
- 贅詞 / 重講分析是啟發式，刪之前仍要判斷
- 不是 DAW：不取代多軌混音、床樂編曲、複雜音效設計

## 前置安裝

需要：

- `ffmpeg` / `ffprobe`
- Python `3.10+`
- `uv`
- 轉錄用 `GROQ_API_KEY`

可選：

- 本地 OpenAI 生圖：`OPENAI_API_KEY`
- Gemini 生圖：`GEMINI_API_KEY` 或 `GOOGLE_API_KEY`

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install -y ffmpeg python3 python3-pip
curl -LsSf https://astral.sh/uv/install.sh | sh
```

macOS：

```bash
brew install ffmpeg python uv
```

接著：

```bash
git clone https://github.com/soanseng/podcast-use.git
cd podcast-use
uv sync
cp .env.example .env
```

## 一鍵安裝成 skill

### 用聊天安裝

- Claude Code 英文：[prompts/install_claude_code_en.txt](prompts/install_claude_code_en.txt)
- Claude Code 繁中：[prompts/install_claude_code_zh-TW.txt](prompts/install_claude_code_zh-TW.txt)
- Codex 英文：[prompts/install_codex_en.txt](prompts/install_codex_en.txt)
- Codex 繁中：[prompts/install_codex_zh-TW.txt](prompts/install_codex_zh-TW.txt)

### 用 shell 安裝

```bash
./scripts/install_skill.sh claude   # Claude Code
./scripts/install_skill.sh codex    # Codex
```

安裝後重啟對應客戶端。

## 建議工作流

把音檔放進資料夾，然後請 Claude Code / Codex 使用 `podcast-use` skill。

手動 helper 流程：

```bash
# 0) 狀態檔
uv run helpers/init_status.py --edit-dir /path/to/edit

# 1) 專有名詞 glossary（建議）
uv run helpers/init_glossary.py --edit-dir /path/to/edit
$EDITOR /path/to/edit/glossary.txt

# 2) 轉錄（預設 turbo；定稿可用 large-v3 + glossary）
uv run helpers/transcribe_groq.py /path/to/audio.wav
uv run helpers/transcribe_groq.py /path/to/audio.wav \
  --model whisper-large-v3 \
  --glossary /path/to/edit/glossary.txt \
  --force

# 3) 打包 + 分析
uv run helpers/pack_transcripts.py --edit-dir /path/to/edit
uv run helpers/analyze_audio.py /path/to/audio.wav --edit-dir /path/to/edit

# 4) agent 寫好 edl.draft.json 後
uv run helpers/validate_edl.py --edit-dir /path/to/edit --edl /path/to/edit/edl.draft.json
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit \
  --edl /path/to/edit/edl.draft.json --preview

# 5) 批准 + final
uv run helpers/approve_edl.py --edit-dir /path/to/edit
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

### 模式

| 模式 | 用途 |
|------|------|
| `cleanup` | 去贅字、死空氣、口誤 |
| `shorten` | 壓長度、去離題 |
| `clip` | 抽精華片段 |
| `takes` | 多 take 選句 |
| `review-only` | 只給建議，不渲染 |
| `publish` | 剪輯鎖定後做完整上架包 |

## 目錄結構

```text
edit/
├── STATUS.md
├── transcripts/
├── analysis/
├── takes_packed.md
├── cut_proposal.md
├── edl.draft.json
├── edl.approved.json
├── edl.json
├── preview.mp3
├── final.mp3
├── final.srt
├── final.mp4
├── show_notes.md
├── timestamps.txt
├── youtube_description.md
└── reels/
```

## EDL

```json
[
  {
    "source": "episode",
    "start": 1.20,
    "end": 7.80,
    "reason": "乾淨開場"
  }
]
```

- draft 寫入 `edl.draft.json`
- 使用者確認後用 `approve_edl.py` 晉升
- final render 應使用 approved EDL

## 聲音工程

Final 預設 spoken-word chain：

1. 前段降噪
2. speech leveling
3. high-pass / low-pass
4. EQ
5. 輕壓縮
6. loudness normalize
7. 後段輕降噪
8. limiter

Preview（`--preview`）會跳過重處理，快速產出 `preview.mp3`。

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --preview
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --edge-pad-ms 60
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-denoise --no-eq
```

## 字幕與發佈

```bash
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit --refine-groq

uv run helpers/init_deliverables.py /path/to/audio.wav --edit-dir /path/to/edit
uv run helpers/render_youtube_video.py /path/to/audio.wav \
  --edit-dir /path/to/edit \
  --image /path/to/edit/cover.png \
  --burn-subtitles

uv run helpers/init_reels_plan.py --edit-dir /path/to/edit
uv run helpers/render_reels.py /path/to/audio.wav --edit-dir /path/to/edit --generate-images
```

字幕精煉規則：不改 cue 數量與時間碼，只修文字；繁中專案優先 zh-Hant；人名品牌跟 glossary。

圖片：

- 有 runtime 內建生圖（如 Codex）時優先用
- 本地 helper 預設 OpenAI `gpt-image-2`
- Gemini 為選配

詳見 [references/publishing.md](references/publishing.md)、[references/images.md](references/images.md)。

## Skill 架構

```text
SKILL.md                 # 精簡主流程：模式、checkpoint、硬規則
references/              # 剪輯判斷、EDL、發佈、圖片細節
helpers/                 # 可執行工具
```

## Helper 一覽

| Helper | 用途 |
|--------|------|
| `init_status.py` | 建立 `STATUS.md` |
| `init_glossary.py` | glossary 模板 |
| `transcribe_groq.py` | 轉錄 |
| `pack_transcripts.py` | 打包 transcript + 統計 |
| `analyze_audio.py` | 靜音 / 贅詞 / 重講提示 |
| `validate_edl.py` | 驗證 EDL 與時長 |
| `approve_edl.py` | draft → approved |
| `render_audio.py` | preview / final 音訊 |
| `build_subtitles.py` | 字幕 |
| `render_youtube_video.py` | YouTube 靜態影片 |
| `render_reels.py` | 直式短影片 |
| `generate_image.py` | 本地生圖 |
| `init_deliverables.py` | 文案骨架 |

各 helper 請用 `--help` 看完整旗標。

## 測試

```bash
uv sync --group dev
uv run pytest
```
