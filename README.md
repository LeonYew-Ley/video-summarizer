[中文文档](README_CN.md)

# Social Summarizer

An AI agent skill that extracts **videos** or **image-text posts** and writes structured notes. Works with **Cursor** and **Claude Code**. The GitHub / local folder name stays `video-summarizer`; the skill `name` is `social-summarizer`.

Run `extract_content.py` first. Then pick the note template from `content_type` (`video` or `post`). Do not guess the type from wording.

## Supported Platforms

| Platform | URL Examples | Kind | Extraction Method | Extra Dependencies |
|---|---|---|---|---|
| **Bilibili** (B站) | `bilibili.com/video/BVxxx` | video | Public API (WBI signing) | None (stdlib only) |
| **YouTube** | `youtube.com/watch?v=xxx`, `youtu.be/xxx` | video | `youtube-transcript-api` | `pip install youtube-transcript-api` |
| **Douyin** (抖音) | `douyin.com/video/`, `v.douyin.com/` | video | Share page + yt-dlp / Whisper | `pip install yt-dlp` (optional) |
| **Douyin notes** | `douyin.com/note/`, share `/note/` | post | Public SEO snapshot of the share page | None |
| **Xiaohongshu** (小红书) | `xiaohongshu.com/`, `xhslink.com/` | video or post | Page parse (`__SETUP_SERVER_STATE__` / `__INITIAL_STATE__`) | None for extract; Whisper for video transcript |
| **Weixin** (公众号) | `mp.weixin.qq.com/s/` | post | Public free article HTML | None |
| **TikTok** | `tiktok.com/@user/video/xxx` | video | yt-dlp | `pip install yt-dlp` |
| **1800+ other sites** | Any URL supported by yt-dlp | video | yt-dlp | `pip install yt-dlp` |

## Features

- **One script, two flows**: URL / page data decides `video` vs `post`
- **Video fallback**: platform API → yt-dlp subtitles → Whisper
- **Timed cues**: when platform subs, VTT, or Whisper segments exist, JSON includes `cues` for chapter timelines
- **Posts**: title, author, body in `subtitle_text`, local images (max 20, all must download)
- **Xiaohongshu images**: `ci.xiaohongshu.com/{token}` rewrite; Live Photo video tracks are skipped
- **Weixin**: public free articles only; paywall / verify / follow-to-read hard-fail with `error`
- **Keyframe screenshots** for video when ffmpeg is installed
- **Cache** by URL hash; `--clear-cache` deletes `cache/`, `screenshots/`, and `images/`

## Quick Start

1. **Download** the skill into the correct directory (see [Installation](#installation))
2. **Install dependencies** for the platforms you need (see [Dependencies](#dependencies))
3. **Paste a URL** (video or post) into Cursor or Claude — the agent runs `extract_content.py` and writes the matching template

## Installation

This skill is **not** a pip package. Cursor/Claude discovers it via `SKILL.md`. Clone or extract the folder to a skills path.

### For Cursor IDE

```bash
git clone https://github.com/LeonYew-Ley/video-summarizer.git \
    ~/.cursor/skills/social-summarizer
```

Or download the ZIP and extract to `~/.cursor/skills/social-summarizer/`.

**Windows path**: `%USERPROFILE%\.cursor\skills\social-summarizer\`

### For Claude Code / Claude Desktop

```bash
git clone https://github.com/LeonYew-Ley/video-summarizer.git \
    ~/.claude/skills/social-summarizer
```

**Windows path**: `%USERPROFILE%\.claude\skills\social-summarizer\`

### How the AI Discovers the Skill

Cursor and Claude scan skills directories for `SKILL.md`. Triggers include platform URLs and Chinese phrases such as 总结视频 / 总结图文 / 总结笔记 / 总结帖子 / 总结公众号. The agent reads `SKILL.md`, runs `extract_content.py`, then formats notes from `content_type`.

## Dependencies

Install **only** what you need, in your normal Python environment.

### Required

- **Python 3.8+** — `python --version`

### Per-Platform Dependencies

| What you want | Install command |
|---|---|
| Bilibili videos | Nothing — stdlib |
| YouTube videos | `pip install youtube-transcript-api` |
| Douyin / Xiaohongshu / Weixin posts | Nothing for metadata + images |
| Douyin / Xiaohongshu videos | Whisper or yt-dlp for transcription |
| TikTok / other sites | `pip install yt-dlp` |

### Optional: Whisper (videos without subtitles)

| Mode | Install command | Notes |
|---|---|---|
| Local (free, offline) | `pip install faster-whisper` | Downloads a model (~150MB–3GB) |
| OpenAI API (fast, paid) | `pip install openai` | Requires API key, ~$0.006/min |
| Audio splitting (API mode) | `pip install pydub` | Long audio upload limits |

### Optional: Keyframe Screenshots

| Tool | Install command | Notes |
|---|---|---|
| ffmpeg | See [ffmpeg installation](#install-ffmpeg) | Video frames |
| Pillow | `pip install Pillow` | Optional image optimization |

### Install Everything at Once

```bash
pip install youtube-transcript-api yt-dlp faster-whisper openai pydub Pillow
```

### Install ffmpeg

Needed for video keyframe screenshots. If missing, the skill falls back to text-only video notes.

**Windows:** `winget install ffmpeg`

**macOS:** `brew install ffmpeg`

**Linux (Ubuntu/Debian):** `sudo apt install ffmpeg`

## Configuration

Edit `config.json` in the skill directory:

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

| Field | Values | Description |
|---|---|---|
| `whisper_mode` | `"disabled"` / `"local"` / `"api"` | Speech recognition. Default `"disabled"`. |
| `openai_api_key` | `"sk-..."` | Only for `whisper_mode: "api"`. |
| `whisper_model` | `"tiny"` … `"large"` | Local model size. `"base"` is balanced. |
| `language` | `"zh"` / `"en"` / … | Whisper hint ([ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes)). |
| `extract_frames` | `true` / `false` | Video keyframes. Default `true`. |
| `frames_per_video` | `1`–`20` | Evenly spaced frames. Default `6`. |
| `cache_ttl_days` | `0`–`365` | Cache / screenshot / image TTL. `0` = keep forever. |

## Cookie Setup (TikTok and some videos)

**Bilibili, public Weixin articles, and most Xiaohongshu / Douyin posts do not need cookies.** TikTok and some video downloads may. If extraction fails:

1. Install "[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)"
2. Visit the site in a browser
3. Export and save as `cookies.txt` in the skill directory

The script also accepts `www.douyin.com_cookies.txt`, `www.xiaohongshu.com_cookies.txt`, and `www.tiktok.com_cookies.txt`.

> **Windows**: Chrome 127+ DPAPI often blocks `yt-dlp --cookies-from-browser`. Export a file instead.

Xiaohongshu explore links need a **fresh** `xsec_token` from a share / live web page. Stale tokens often 404.

## Output Format

`extract_content.py` prints JSON to stdout.

**Video** (`content_type` is always `video`):

```json
{
    "content_type": "video",
    "title": "Video Title",
    "author": "Uploader Name",
    "duration": "00:19",
    "description": "Video description",
    "platform": "youtube",
    "url": "https://...",
    "source": "yt_dlp_subs",
    "subtitle_text": "Full transcript...",
    "cues": [
        {"start": 1.2, "end": 3.36, "text": "All right, so here we are..."}
    ],
    "frames": [
        {"path": "/absolute/path/to/frame_001.jpg", "timestamp": "00:45"}
    ]
}
```

**Post** (`content_type` is always `post`):

```json
{
    "content_type": "post",
    "title": "Note title",
    "author": "Author",
    "description": "Caption or article body",
    "platform": "xiaohongshu",
    "url": "https://...",
    "source": "note_page",
    "subtitle_text": "Caption or article body",
    "images": [
        {"path": "/absolute/path/to/images/<hash>/01.png", "index": 1}
    ]
}
```

| Field | Description |
|---|---|
| `content_type` | `video` or `post` only |
| `cues` | Timed segments in seconds. Video only, when timing exists |
| `images` | Local post images. Empty list if none |
| `images_truncated` | `true` plus original count when the page had more than 20 images |
| `frames` | Video keyframes when ffmpeg + `extract_frames` |
| `error` | Present when extraction failed |

The agent then writes Markdown: video chapters use `> mm:ss – mm:ss` under each heading; posts use a separate figure-by-figure template.

## File Structure

```
social-summarizer/
├── SKILL.md              # Skill definition
├── extract_content.py    # Extraction script
├── config.json           # User configuration
├── requirements.txt      # Optional pip list
├── README.md             # English docs
├── README_CN.md          # Chinese docs
├── INTRODUCE.md          # Architecture
├── .gitignore            # cache, screenshots, images, cookies
├── cache/                # (auto) extraction JSON
├── screenshots/          # (auto) video frames
└── images/               # (auto) post images
```

## Standalone Usage

```bash
python extract_content.py "https://www.bilibili.com/video/BV1xxxxxx"
python extract_content.py "https://mp.weixin.qq.com/s/xxxxxxxx"
```

```bash
python extract_content.py "https://youtu.be/xxxxx" | jq '.content_type, .title, .source'
```

Clear cache, screenshots, and post images:

```bash
python extract_content.py --clear-cache
```

## Troubleshooting

| Problem | Solution |
|---|---|
| "No subtitles or transcript could be extracted" | Enable Whisper in `config.json` |
| YouTube 403 | VPN or retry; IP may be blocked |
| Douyin **note** fails | Share SSR may be empty; the script falls back to the public SEO snapshot. `/note/` must stay `post`, not video |
| Douyin **video** fails | Export cookies or enable Whisper |
| Xiaohongshu 404 / 300031 | Use a fresh share / explore URL with a live `xsec_token` |
| Weixin `error` | Paywall, follow-to-read, captcha, or environment check — not extracted |
| `yt-dlp` not found | `pip install yt-dlp` (or `python -m yt_dlp`) |
| No screenshots | Install ffmpeg. Optional |
| Stale cache | `python extract_content.py --clear-cache` |

## License

MIT
