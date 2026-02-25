[中文文档](README_CN.md)

# Multi-Video-Summarizer

An AI agent skill that extracts subtitles/transcripts from video platforms and generates structured summary notes with keyframe screenshots. Works with **Cursor** and **Claude Code**.

## Supported Platforms

| Platform | URL Examples | Extraction Method | Extra Dependencies |
|---|---|---|---|
| **Bilibili** (B站) | `bilibili.com/video/BVxxx` | Public API (WBI signing) | None (stdlib only) |
| **YouTube** | `youtube.com/watch?v=xxx`, `youtu.be/xxx` | `youtube-transcript-api` | `pip install youtube-transcript-api` |
| **Douyin** (抖音) | `douyin.com/`, `v.douyin.com/xxx` | Direct API + yt-dlp | `pip install yt-dlp` |
| **Xiaohongshu** (小红书) | `xiaohongshu.com/`, `xhslink.com/` | Direct page parsing (no cookie) | None for extraction; Whisper for transcription |
| **TikTok** | `tiktok.com/@user/video/xxx` | yt-dlp | `pip install yt-dlp` |
| **1800+ other sites** | Any URL supported by yt-dlp | yt-dlp | `pip install yt-dlp` |

## Features

- **Multi-platform subtitle extraction** with automatic platform detection
- **3-layer fallback**: platform API → yt-dlp subtitles → Whisper speech recognition
- **Cookie-free for major platforms**: Bilibili, Douyin, and Xiaohongshu all work without login or cookies
- **Keyframe screenshots**: automatically extracts video frames and embeds them in summaries
- **Caching**: extracted results are cached locally to avoid redundant downloads
- **BibiGPT-style output**: structured markdown notes with sections, highlights, and tags

## Quick Start

1. **Download** the skill into the correct directory (see [Installation](#installation))
2. **Install dependencies** for the platforms you need (see [Dependencies](#dependencies))
3. **Paste a video URL** into Cursor or Claude — the AI will automatically detect and summarize it

## Installation

This skill is **not** a pip package. It is a directory of files that Cursor/Claude discovers via the `SKILL.md` convention. You install it by cloning or downloading the folder to a specific location.

### For Cursor IDE

```bash
# Clone into Cursor's skills directory
git clone https://github.com/keepongo/video-summarizer.git \
    ~/.cursor/skills/multi-video-summarizer
```

Or download the ZIP and extract to `~/.cursor/skills/multi-video-summarizer/`.

**Windows path**: `%USERPROFILE%\.cursor\skills\multi-video-summarizer\`

### For Claude Code / Claude Desktop

```bash
git clone https://github.com/keepongo/video-summarizer.git \
    ~/.claude/skills/multi-video-summarizer
```

**Windows path**: `%USERPROFILE%\.claude\skills\multi-video-summarizer\`

### How the AI Discovers the Skill

Cursor and Claude automatically scan their skills directories for folders containing a `SKILL.md` file. When you paste a video URL (e.g., `bilibili.com`, `youtube.com`, `douyin.com`), the AI reads `SKILL.md`, which tells it how to run `video_subtitle.py` and format the output. No manual activation is needed.

## Dependencies

Install **only** what you need. All `pip install` commands should be run in your normal Python environment (not inside the skill directory).

### Required

- **Python 3.8+** — verify with `python --version`

### Per-Platform Dependencies

| What you want | Install command |
|---|---|
| Bilibili videos | Nothing — uses Python stdlib |
| YouTube videos | `pip install youtube-transcript-api` |
| Douyin videos | Nothing for metadata; Whisper or yt-dlp for transcription |
| Xiaohongshu videos | Nothing for metadata + video; Whisper for transcription |
| TikTok / other sites | `pip install yt-dlp` |

### Optional: Whisper Transcription (for videos without subtitles)

| Mode | Install command | Notes |
|---|---|---|
| Local (free, offline) | `pip install faster-whisper` | Downloads a model (~150MB–3GB depending on size) |
| OpenAI API (fast, paid) | `pip install openai` | Requires API key, ~$0.006/min |
| Audio splitting (API mode) | `pip install pydub` | Splits long audio for API upload limits |

### Optional: Keyframe Screenshots

| Tool | Install command | Notes |
|---|---|---|
| ffmpeg | See [ffmpeg installation](#install-ffmpeg) | Required for frame extraction |
| Pillow | `pip install Pillow` | Optional image optimization |

### Install Everything at Once

```bash
pip install youtube-transcript-api yt-dlp faster-whisper openai pydub Pillow
```

### Install ffmpeg

ffmpeg is needed for extracting keyframe screenshots from videos. If not installed, the skill gracefully falls back to text-only summaries.

**Windows:**
```bash
winget install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install ffmpeg
```

## Configuration

Edit `config.json` in the skill directory to customize behavior:

```json
{
    "whisper_mode": "disabled",
    "openai_api_key": "",
    "whisper_model": "base",
    "language": "zh",
    "extract_frames": true,
    "frames_per_video": 6,
    "cache_ttl_days": 7
}
```

### Configuration Fields

| Field | Values | Description |
|---|---|---|
| `whisper_mode` | `"disabled"` / `"local"` / `"api"` | Speech recognition mode. Default `"disabled"` — only subtitle-based extraction. |
| `openai_api_key` | `"sk-..."` | Your OpenAI API key. Only needed when `whisper_mode` is `"api"`. |
| `whisper_model` | `"tiny"` / `"base"` / `"small"` / `"medium"` / `"large"` | Local Whisper model size. `"base"` is a good balance of speed and accuracy. |
| `language` | `"zh"` / `"en"` / `"ja"` / ... | Hint language for Whisper. Use [ISO 639-1 codes](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes). |
| `extract_frames` | `true` / `false` | Whether to extract keyframe screenshots from videos. Default `true`. |
| `frames_per_video` | `1`–`20` | Number of evenly-spaced frames to extract. Default `6`. |
| `cache_ttl_days` | `0`–`365` | Days to keep cached results and screenshots. Default `7`. Set to `0` to keep forever. |

### Switching Whisper Modes

**Enable local Whisper** (free, runs on your machine):
```json
{
    "whisper_mode": "local",
    "whisper_model": "base",
    "language": "zh"
}
```
First run will download the model (~150MB for `base`). Model sizes ranked by quality: `tiny` < `base` < `small` < `medium` < `large` (up to ~3GB).

**Enable OpenAI Whisper API** (fast, requires API key):
```json
{
    "whisper_mode": "api",
    "openai_api_key": "sk-your-key-here",
    "language": "zh"
}
```

**Disable Whisper** (subtitles only, no speech recognition):
```json
{
    "whisper_mode": "disabled"
}
```

## Cookie Setup for TikTok (and other platforms)

**Bilibili, Douyin, and Xiaohongshu work without any cookies.** The script uses direct API parsing for these platforms. TikTok and some other platforms may still require browser cookies. If extraction fails:

1. Install the browser extension "[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)"
2. Visit `douyin.com` (or `xiaohongshu.com`) in your browser — no login required
3. Click the extension icon and export cookies
4. Save the file as `cookies.txt` in the skill directory

The script auto-detects cookie files named `cookies.txt`, `www.douyin.com_cookies.txt`, etc.

> **Note for Windows users**: Chrome 127+ uses DPAPI encryption for cookies, which prevents `yt-dlp --cookies-from-browser` from working. The manual cookie export above is the recommended workaround. (Windows 用户注意：Chrome 127+ 的 DPAPI 加密会导致 yt-dlp 无法自动读取浏览器 cookies，建议手动导出。)

## Output Format

The extraction script (`video_subtitle.py`) outputs JSON to stdout:

```json
{
    "title": "Video Title",
    "author": "Uploader Name",
    "duration": "05:30",
    "description": "Video description",
    "platform": "bilibili",
    "url": "https://...",
    "source": "whisper_local",
    "subtitle_text": "Full transcript text...",
    "frames": [
        {"path": "/absolute/path/to/frame_001.jpg", "timestamp": "00:45"},
        {"path": "/absolute/path/to/frame_002.jpg", "timestamp": "01:30"}
    ]
}
```

| Field | Description |
|---|---|
| `source` | How the text was obtained: `subtitle`, `ai_conclusion`, `transcript_api`, `yt_dlp_subs`, `whisper_local`, `whisper_api` |
| `frames` | Array of keyframe screenshots with absolute file path and timestamp. Only present if ffmpeg is installed and `extract_frames` is enabled. |
| `error` | Error message if extraction failed. Not present on success. |

The AI then transforms this into a structured markdown summary with section headers, highlights, hashtags, and embedded screenshots.

## File Structure

```
multi-video-summarizer/
├── SKILL.md              # Skill definition (triggers AI discovery)
├── video_subtitle.py     # Core extraction script (~1500 lines)
├── config.json           # User configuration
├── requirements.txt      # pip dependencies list
├── README.md             # English documentation
├── README_CN.md          # Chinese documentation (中文文档)
├── INTRODUCE.md          # Project architecture and file guide
├── .gitignore            # Excludes cache, screenshots, cookies
├── cache/                # (auto-created) Cached extraction results
└── screenshots/          # (auto-created) Keyframe images
```

## Standalone Usage

You can also run the script directly from the command line:

```bash
python video_subtitle.py "https://www.bilibili.com/video/BV1xxxxxx"
```

This outputs the JSON result to stdout. Combine with `jq` for quick inspection:

```bash
python video_subtitle.py "https://youtu.be/xxxxx" | jq '.title, .source'
```

Clear all cached results and screenshots:

```bash
python video_subtitle.py --clear-cache
```

## Troubleshooting

| Problem | Solution |
|---|---|
| "No subtitles or transcript could be extracted" | Enable Whisper in `config.json` — many videos lack built-in subtitles |
| YouTube extraction fails with 403 | IP may be blocked by YouTube. Try a VPN, or use the WebFetch tool in Cursor |
| Douyin extraction fails | Douyin usually works without cookies. If it fails, export cookies manually (see [Cookie Setup](#cookie-setup-for-tiktok-and-other-platforms)) |
| Xiaohongshu extraction fails | XHS uses direct page parsing (no cookies). If video download fails, check your network connection |
| `yt-dlp` not found | Run `pip install yt-dlp`, or if installed but not on PATH, the script falls back to `python -m yt_dlp` |
| ffmpeg not found / no screenshots | Install ffmpeg (see [Install ffmpeg](#install-ffmpeg)). Frame extraction is optional and skipped gracefully |
| Whisper model download hangs | Check your network connection. Local models download from Hugging Face on first use |
| Stale/outdated cached result | Cache expires after 7 days by default (configurable via `cache_ttl_days`). To force refresh, run `python video_subtitle.py --clear-cache` |

## License

MIT
