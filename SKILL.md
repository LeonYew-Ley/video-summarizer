---
name: social-summarizer
description: "Summarize video or image-text posts from social platforms into structured notes. Videos: Bilibili, YouTube, Douyin, Xiaohongshu, TikTok, and 1800+ sites via yt-dlp. Posts: Xiaohongshu notes, Douyin image posts, Weixin articles. Triggers on those URLs, or Chinese requests like '总结视频', '视频笔记', '总结图文', '总结笔记', '总结帖子', '总结公众号'."
---

# Social Summarizer

Extract video transcripts or image-text posts, then write structured notes. No login or cookies required for public content.

**Always run the extraction script first.** Then pick the note template from `content_type` in the JSON (`video` or `post`). Do not guess the type from the user's wording.

## Supported Platforms

| Platform | URL patterns | Extraction method |
|---|---|---|
| Bilibili (B站) | `bilibili.com/video/`, `b23.tv/`, `BV*` | Public API (WBI signing) |
| YouTube | `youtube.com/watch`, `youtu.be/`, `youtube.com/shorts/` | `youtube-transcript-api` |
| Douyin (抖音) | `douyin.com/`, `v.douyin.com/` | Share page / public SEO snapshot (notes) or `yt-dlp` (video) |
| Xiaohongshu (小红书) | `xiaohongshu.com/`, `xhslink.com/` | Page parse (video or post) |
| Weixin (公众号) | `mp.weixin.qq.com/` | Public free article HTML |
| TikTok | `tiktok.com/` | `yt-dlp` |
| Any other | Any URL supported by yt-dlp (1800+ sites) | `yt-dlp` |

## Prerequisites

Ensure Python 3 is available:

```bash
python --version
```

## Dependency Check

Before running the extraction script, check and install required dependencies based on the video platform:

**For Bilibili videos** -- no extra dependencies needed (uses Python stdlib only).

**For YouTube videos:**
```bash
pip install youtube-transcript-api
```

**For Douyin, Xiaohongshu, TikTok, or any other platform:**
```bash
pip install yt-dlp
```

**Optional -- Whisper transcription** (for videos without subtitles):
- OpenAI API mode: `pip install openai`
- Local mode: `pip install faster-whisper`
- Configure in `config.json` (see Whisper Setup below)

Only install what is needed. If the user provides a Bilibili URL, skip dependency installation entirely.

## Workflow

### Step 1: Install Dependencies (if needed)

Check the video URL to determine the platform. If it's NOT a Bilibili URL, ensure the required package is installed:

```bash
pip install youtube-transcript-api yt-dlp
```

If these are already installed, skip this step.

### Step 2: Extract Content

Run the extraction script with the URL:

```bash
python "<skill_path>/extract_content.py" "<URL>"
```

Replace `<skill_path>` with the absolute path to this skill's directory, and `<URL>` with the link provided by the user.

The script automatically:
1. Detects the platform and page type from the URL / page data
2. For video: tries platform subtitle APIs, then yt-dlp subs, then Whisper
3. For post: extracts title, body, and local image paths (max 20, all-or-nothing)

The script outputs a JSON object to stdout containing:
- `content_type` - `video` or `post`. Use this to pick the template below
- `title` - Title
- `author` - Uploader / author name
- `duration` - Video duration (video only)
- `description` - Description / caption
- `platform` - `bilibili`, `youtube`, `douyin`, `xiaohongshu`, `tiktok`, `weixin`, or `generic`
- `url` - Canonical URL
- `source` - Extraction method: `subtitle`, `ai_conclusion`, `transcript_api`, `yt_dlp_subs`, `whisper_local`, `whisper_api`, `note_page`, ...
- `subtitle_text` - Transcript or post body (if available)
- `cues` - Timed transcript segments `{start, end, text}` in seconds. Present only for video when timing is available (platform subs, VTT, or Whisper segments)
- `frames` - Video keyframe screenshots (if ffmpeg is installed and `extract_frames` is enabled). Each frame has `path` and `timestamp`
- `images` - Local image paths for posts
- `error` - Error message (if extraction failed)

### Step 3: Handle Errors

If the output contains an `error` field:

1. Check if the required dependencies are installed for that platform
2. If the error mentions missing packages, install them and retry
3. If Whisper is not enabled and no subtitles were found, suggest the user enable Whisper in `config.json`
4. After fixing, retry the extraction

### Step 4: Choose Template by `content_type`

- `content_type == "video"` → video template (timeline quotes under each chapter)
- `content_type == "post"` → post template (no timestamps, no spoken-word assumptions)

### Step 4a: Video Notes (BibiGPT Style)

When subtitle text is successfully extracted, summarize it into this BibiGPT-style format.
Use the EXACT structure below, including emojis, section naming, and formatting.

Put the time range on the line **under** the chapter title as a Markdown blockquote. Do **not** put times in the title.

After grouping the transcript into topics, take the first and last `cues` that belong to that topic and write `> mm:ss – mm:ss` (use `h:mm:ss` if over an hour). Rounding to the nearest second is fine.

Write `> 无时间轴` **only** when `cues` is missing or empty: no timed platform/VTT subtitles **and** Whisper did not produce segments (disabled, missing, or failed), leaving untimed text such as Bilibili AI conclusion. Then briefly say why. Do not treat "no official captions" as "no timeline" if Whisper cues exist.

**If `frames` array is present in the JSON output**, embed one screenshot per content section using the Read tool to view the frame image file, then insert it with markdown image syntax after the timeline quote. Match frames to sections by timestamp order -- assign one frame per section sequentially. If there are more sections than frames, some sections will have no image. If there are more frames than sections, distribute evenly.

```markdown
# AI 一键总结：[{title}]({url})

# 🤖 {title} — 通俗解释


### 🏷️ {Section 1 Title}
> 03:12 – 07:45
![{Section 1 Title}]({frame_path_for_section_1})
- {Key point from transcript, preserving original examples and analogies}
- {Another key point}
*   {Sub-point or example}
*   {Sub-point or example}


### 💡 {Section 2 Title}
> 07:46 – 12:03
![{Section 2 Title}]({frame_path_for_section_2})
- {Content organized by topic}
- {Preserve vivid analogies from the video}


### 🧠 {Section 3 Title}
> 无时间轴
- {Use this quote only when cues are absent; explain why in the notes}


### 🍎 {Section 4 Title}
> 18:01 – 21:20
- {More content sections as needed}


(... more sections using rotating emojis: 🏷️ 💡 🧠 🍎 🔑 🔢 🧱 🎯 ...)


### Summary
- {One paragraph summarizing the entire video content concisely}


### Highlights
*   🧠 {Highlight 1 with emoji} [#tag1] [#tag2] [#tag3]
*   🔪 {Highlight 2 with emoji} [#tag1] [#tag2] [#tag3]
*   🧮 {Highlight 3 with emoji} [#tag1] [#tag2] [#tag3]
*   🔢 {Highlight 4 with emoji} [#tag1] [#tag2] [#tag3]
*   🧱 {Highlight 5 with emoji} [#tag1] [#tag2] [#tag3]


[#tag1] [#tag2] [#tag3] [#tag4] [#tag5]


### Questions
*   {Thought-provoking question 1 related to the video content}
*   {Thought-provoking question 2 that extends the topic}
```

Guidelines for summarization:
- Use the original language of the subtitle (Chinese for Chinese videos, English for English videos, etc.)
- Use emoji-prefixed section headers (### 🏷️, ### 💡, ### 🧠, etc.)
- Use `-` for main bullet points and `*` (with 4 spaces indent) for sub-points/examples
- Group content into logical sections based on topic flow
- Preserve vivid examples, analogies and metaphors from the video
- Keep the summary concise but comprehensive
- Generate 5 highlights with emojis and 3 hashtags each
- Generate 2 thought-provoking follow-up questions
- Add 5 relevant hashtag topics at the end
- If the source is "ai_conclusion", note that the summary comes from B站's built-in AI summary feature
- If the source is "whisper_local" or "whisper_api", note that the transcript was generated via speech recognition and may contain minor inaccuracies
- **Chapter timeline**: Place `> mm:ss – mm:ss` immediately under each `### ` header, sourced from `cues`. If there are no cues, write `> 无时间轴` and say why
- **Keyframe images**: When frames are provided, embed them using `![title](absolute_path)` syntax. Each section should have at most one image, placed after the timeline quote. Use the absolute `path` value from the frames array as-is

### Step 4b: Post Notes

Use this **separate** post template. Do not reuse the video template. No timestamps, no spoken-word / 口播 assumptions.

If the model cannot read images, say so in the first paragraph, then summarize only from `subtitle_text`. Do not invent figure content. If `images_truncated` is true, say later images were omitted.

```markdown
# 图文总结：[{title}]({url})

作者：{author} · {platform}

### 原文要点
- {caption / body points from subtitle_text}

### 图 1
![{title} 图1]({images[0].path})
- {what this figure shows}

### 图 2
![{title} 图2]({images[1].path})
- {what this figure shows}

(... 图 3…N in order ...)

### Summary
- {one paragraph overall}

### Highlights
*   {highlight with emoji} [#tag1] [#tag2] [#tag3]
*   {highlight}
*   {highlight}

[#tag1] [#tag2] [#tag3] [#tag4] [#tag5]

### Questions
*   {follow-up question}
*   {follow-up question}
```

## Whisper Setup (Optional)

For videos without subtitles, Whisper can transcribe the audio. Edit `config.json` in this skill's directory:

**Option A -- OpenAI Whisper API** (fast, requires API key, costs ~$0.006/min):
```json
{
    "whisper_mode": "api",
    "openai_api_key": "sk-your-key-here",
    "language": "zh"
}
```

**Option B -- Local faster-whisper** (free, requires model download ~1-3GB):
```json
{
    "whisper_mode": "local",
    "whisper_model": "base",
    "language": "zh"
}
```

Model sizes: `tiny` (fast, less accurate) / `base` (balanced) / `small` / `medium` / `large` (slow, most accurate).

## Douyin / Xiaohongshu / TikTok Cookie Setup

These platforms require browser cookies for yt-dlp to access video content. The script tries `--cookies-from-browser` automatically, but on Windows with Chrome 127+ this often fails due to DPAPI encryption.

**Recommended: export cookies.txt manually**

1. Install the browser extension "[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)"
2. Open `douyin.com` (or `xiaohongshu.com`) in your browser (login is NOT required, just visit the page)
3. Click the extension icon and export cookies
4. Save the file as `cookies.txt` in this skill's directory (`<skill_path>/cookies.txt`)

The script will automatically detect and use this file for Douyin/Xiaohongshu/TikTok requests.

## Keyframe Screenshots (Optional)

The script can extract keyframe screenshots from videos to embed in the summary. This requires `ffmpeg` to be installed.

To enable/disable, edit `config.json`:
```json
{
    "extract_frames": true,
    "frames_per_video": 6
}
```

- `extract_frames`: `true` (default) to capture keyframes, `false` to skip
- `frames_per_video`: number of evenly-spaced frames to extract (default `6`)

Screenshots are cached in the `screenshots/` directory. If ffmpeg is not installed, frame extraction is silently skipped.
