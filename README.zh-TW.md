# podcast-use

以對話驅動的 podcast / spoken-word 剪輯 skill，適用於 Claude Code 與 Codex。

[English README](README.md)

## 這個 skill 可以做什麼

- 用 Groq Whisper 轉錄音訊
- 把 transcript 打包成適合閱讀與剪輯的 markdown
- 讓 LLM 根據內容產生 `edl.json`
- 用 `ffmpeg` 輸出剪好的 `final.mp3`
- 套用 podcast 向的聲音工程
- 產生字幕 `final.srt`
- 產生 YouTube 靜態影片 `final.mp4`
- 用 Gemini 生成封面圖與 reels 圖片
- 產出 reels
- 產出 `show_notes.md`、`timestamps.txt`、`youtube_description.md`

## 前置安裝

需要先有：

- `ffmpeg`
- Python `3.10+`
- `uv`

各平台建議安裝方式：

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

Windows：

- 安裝 `ffmpeg` 並加入 `PATH`
- 安裝 Python `3.10+`
- 依照 https://docs.astral.sh/uv/getting-started/installation/ 安裝 `uv`

Arch Linux：

```bash
sudo pacman -S ffmpeg python uv
```

接著設定 repo：

```bash
git clone https://github.com/soanseng/podcast-use.git
cd podcast-use
uv sync
cp .env.example .env
```

再編輯 `.env`：

```bash
$EDITOR .env
```

## 一鍵安裝成 skill

Claude Code：

```bash
git clone https://github.com/soanseng/podcast-use.git && cd podcast-use && ./scripts/install_skill.sh claude
```

Codex：

```bash
git clone https://github.com/soanseng/podcast-use.git && cd podcast-use && ./scripts/install_skill.sh codex
```

安裝完後，重啟對應客戶端。

## 聲音工程

目前預設的 spoken-word chain 是用 `ffmpeg` 近似廣播 / Audacity 類型流程，不是逐項完全複製 Audacity 演算法，但順序和目的接近：

1. 前段降噪
2. 前段 speech leveling，近似第一次正規化
3. high-pass 去低頻 rumble
4. low-pass 壓高頻 hiss
5. spoken-word EQ
6. 輕壓縮
7. loudness normalize
8. 後段輕降噪
9. limiter

對應 helper：

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

可選擇關閉部分處理：

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-denoise
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-leveler
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-eq
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-compressor
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-normalize
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-post-denoise
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-limiter
```

## 發佈包

如果目標是上架，這個 skill 預設應該一起產出：

- `final.mp3`
- `final.srt`
- `final.mp4`
- `reels/`
- `show_notes.md`
- `timestamps.txt`
- `youtube_description.md`

## 圖片流程

生成封面或 reels 圖片前，skill 應該先問：

- 要不要把文字直接做進圖片
- 想要什麼風格
- 如果沒想法，先給 2 到 3 個風格方向選
- reels 要不要每支同一風格，或每支都不同

## glossary

如果內容有：

- 人名
- 品牌名
- 英中混用名詞
- 台語詞

建議先建立 `edit/glossary.txt`，一行一個詞，再重跑最終版轉錄。
