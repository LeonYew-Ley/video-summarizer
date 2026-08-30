[中文文档](README_CN.md)

# Social Summarizer

An AI Agent Skill for Cursor and Claude Code: paste a video or image-text post URL, and the agent extracts the content and writes a structured note.

It supports subtitle retrieval, Whisper transcription, video keyframes, post images, and URL-based caching. Both the repository and Skill are named `social-summarizer`.

## Supported Platforms

| Platform | Kind | Extra dependency or limitation |
|---|---|---|
| Bilibili | Video | None |
| YouTube | Video | `youtube-transcript-api` |
| Douyin | Video, post | Videos may need `yt-dlp` or Whisper |
| Xiaohongshu | Video, post | URL must include a valid `xsec_token`; video transcription needs Whisper |
| Weixin | Post | Public free articles only |
| TikTok | Video | `yt-dlp` |
| Other yt-dlp sites | Video | `yt-dlp` |

## Installation and Usage

This Skill is not a pip package. Copy the following block to the agent in your current environment:

```text
Install Social Summarizer as my user-level Agent Skill.

Repo: https://github.com/LeonYew-Ley/social-summarizer
Skill name: social-summarizer

Requirements:
1. Install it in this environment's user-level skills directory (this is not a pip package).
2. A plain git clone is enough. Name the folder social-summarizer; its root must contain SKILL.md and extract_content.py.
3. After installation, report the final path and any dependencies still missing for the current platform.
```

After installation, paste a supported URL into Cursor or Claude. The agent runs the extractor and writes the appropriate note for the detected content type.

To get JSON directly from a terminal:

```bash
python extract_content.py "https://example.com/video-or-post"
```

To clear cached results, video frames, and post images:

```bash
python extract_content.py --clear-cache
```

## Dependencies and Configuration

Python 3.8+ is required. Install other dependencies only when needed:

| Purpose | Install or prepare |
|---|---|
| YouTube transcripts | `pip install youtube-transcript-api` |
| TikTok, other sites, or some video downloads | `pip install yt-dlp` |
| Local Whisper | `pip install faster-whisper` |
| OpenAI Whisper API | `pip install openai`; add `pydub` for long audio if needed |
| Video keyframes | Install ffmpeg; `pip install Pillow` is optional |

ffmpeg commands: Windows `winget install ffmpeg`, macOS `brew install ffmpeg`, Ubuntu/Debian `sudo apt install ffmpeg`.

`config.json` is optional; the defaults work without editing it. Common fields:

| Field | Description |
|---|---|
| `whisper_mode` | `disabled`, `local`, or `api` |
| `openai_api_key` | Required only in API mode |
| `whisper_model` | Local model; defaults to `base` |
| `language` | Whisper language hint; defaults to `zh` |
| `extract_frames` | Whether to extract video keyframes |
| `frames_per_video` | Number of keyframes; defaults to 6 |
| `cache_ttl_days` | Cache lifetime; `0` keeps files forever |

## Troubleshooting

### Xiaohongshu 404 / 300031

Explore and note URLs must include a fresh `xsec_token` copied from the website:

```text
https://www.xiaohongshu.com/explore/<note_id>?xsec_token=AB...=&xsec_source=pc_feed
```

- Do not reconstruct or remove `xsec_token`; an expired token usually returns 404 or `error_code=300031`.
- Keep `xsec_source` when present. Short links can redirect, but the final page still needs a valid token.

### Do I need cookies?

Bilibili, public Weixin articles, and most Douyin or Xiaohongshu posts do not need cookies. If TikTok or a video download fails, export `cookies.txt` with [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) and place it in the Skill root.

The script also recognizes `www.douyin.com_cookies.txt`, `www.xiaohongshu.com_cookies.txt`, and `www.tiktok.com_cookies.txt`. Chrome 127+ on Windows may block `yt-dlp --cookies-from-browser`; exporting a file is more reliable.

### Other problems

| Problem | Solution |
|---|---|
| No transcript | Enable Whisper in `config.json` |
| YouTube 403 | Retry or change networks; the current IP may be restricted |
| Douyin video fails | Export cookies or enable Whisper |
| Weixin returns `error` | Paywalls, follow-to-read, captchas, and environment checks are unsupported |
| `yt-dlp` not found | Run `pip install yt-dlp` |
| No video keyframes | Install ffmpeg |
| Stale cache | Run `python extract_content.py --clear-cache` |

See [INTRODUCE.md](INTRODUCE.md) for the workflow, type detection, and JSON contract.

## License

MIT
