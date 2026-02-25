[English](README.md)

# Multi-Video-Summarizer

一个 AI Agent Skill（AI 代理技能），可从多个视频平台提取字幕/转录文本，并生成带有关键帧截图的结构化总结笔记。适用于 **Cursor IDE** 和 **Claude Code**。

## 支持的平台

| 平台 | URL 示例 | 提取方式 | 额外依赖 |
|---|---|---|---|
| **B站**（Bilibili） | `bilibili.com/video/BVxxx` | 公开 API（WBI 签名） | 无（仅用 Python 标准库） |
| **YouTube** | `youtube.com/watch?v=xxx`、`youtu.be/xxx` | `youtube-transcript-api` | `pip install youtube-transcript-api` |
| **抖音**（Douyin） | `douyin.com/`、`v.douyin.com/xxx` | 直接 API 解析（无需 Cookie） | 无需额外依赖；Whisper 用于转录 |
| **小红书**（Xiaohongshu） | `xiaohongshu.com/`、`xhslink.com/` | 直接页面解析（无需 Cookie） | 无需额外依赖；Whisper 用于转录 |
| **TikTok** | `tiktok.com/@user/video/xxx` | yt-dlp | `pip install yt-dlp` |
| **1800+ 其他网站** | 任何 yt-dlp 支持的 URL | yt-dlp | `pip install yt-dlp` |

## 功能特性

- **多平台字幕提取**：自动检测视频平台
- **三层降级策略**：平台 API → yt-dlp 字幕 → Whisper 语音识别
- **主流平台免 Cookie**：B站、抖音、小红书均无需登录或 Cookie 即可使用
- **关键帧截图**：自动从视频中提取画面并嵌入到总结笔记中
- **结果缓存**：已提取的结果本地缓存，避免重复下载
- **BibiGPT 风格输出**：结构化 Markdown 笔记，包含章节、亮点和标签

## 快速开始

1. **下载** Skill 到指定目录（参见 [安装](#安装)）
2. **安装依赖**（参见 [依赖安装](#依赖安装)）
3. **粘贴视频链接** 到 Cursor 或 Claude 对话中，AI 会自动识别并总结

## 安装

本 Skill **不是** pip 包，不能通过 `pip install` 安装。它是一个文件目录，Cursor/Claude 通过识别其中的 `SKILL.md` 文件来发现和使用。安装方式是将整个文件夹克隆或下载到指定位置。

### Cursor IDE

```bash
# 克隆到 Cursor 的 skills 目录
git clone https://github.com/keepongo/video-summarizer.git \
    ~/.cursor/skills/multi-video-summarizer
```

或者下载 ZIP 压缩包，解压到 `~/.cursor/skills/multi-video-summarizer/`。

**Windows 路径**：`%USERPROFILE%\.cursor\skills\multi-video-summarizer\`

### Claude Code / Claude Desktop

```bash
git clone https://github.com/keepongo/video-summarizer.git \
    ~/.claude/skills/multi-video-summarizer
```

**Windows 路径**：`%USERPROFILE%\.claude\skills\multi-video-summarizer\`

### AI 如何发现此 Skill

Cursor 和 Claude 会自动扫描 skills 目录下包含 `SKILL.md` 的文件夹。当你粘贴视频链接（如 `bilibili.com`、`youtube.com`、`douyin.com`），AI 会读取 `SKILL.md` 中的说明，调用 `video_subtitle.py` 提取字幕，然后按照模板格式化输出。无需手动激活。

## 依赖安装

按需安装即可。所有 `pip install` 命令应在你的 **正常 Python 环境** 中执行（不是在 skill 目录内）。

### 必需

- **Python 3.8+** — 使用 `python --version` 检查

### 按平台安装

| 用途 | 安装命令 |
|---|---|
| B站视频 | 无需安装任何额外依赖 |
| YouTube 视频 | `pip install youtube-transcript-api` |
| 抖音视频 | 无需额外依赖（元数据自动获取）；Whisper 或 yt-dlp 用于转录 |
| 小红书视频 | 无需额外依赖（视频直接下载）；Whisper 用于转录 |
| TikTok / 其他网站 | `pip install yt-dlp` |

### 可选：Whisper 语音转文字（用于没有字幕的视频）

| 模式 | 安装命令 | 说明 |
|---|---|---|
| 本地模式（免费、离线） | `pip install faster-whisper` | 首次运行会下载模型（约 150MB ~ 3GB） |
| OpenAI API 模式（快速、付费） | `pip install openai` | 需要 API Key，约 $0.006/分钟 |
| 音频分割（API 模式用） | `pip install pydub` | 将长音频分片以适应 API 上传限制 |

### 可选：关键帧截图

| 工具 | 安装命令 | 说明 |
|---|---|---|
| ffmpeg | 参见 [安装 ffmpeg](#安装-ffmpeg) | 截图功能必需 |
| Pillow | `pip install Pillow` | 可选的图片优化 |

### 一键安装全部依赖

```bash
pip install youtube-transcript-api yt-dlp faster-whisper openai pydub Pillow
```

### 安装 ffmpeg

ffmpeg 用于从视频中提取关键帧截图。如果未安装，Skill 会优雅降级为纯文字总结。

**Windows：**
```bash
winget install ffmpeg
```

**macOS：**
```bash
brew install ffmpeg
```

**Linux（Ubuntu/Debian）：**
```bash
sudo apt install ffmpeg
```

## 配置

编辑 skill 目录中的 `config.json` 来自定义行为：

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

### 配置字段说明

| 字段 | 可选值 | 说明 |
|---|---|---|
| `whisper_mode` | `"disabled"` / `"local"` / `"api"` | 语音识别模式。默认 `"disabled"` — 仅使用字幕提取。 |
| `openai_api_key` | `"sk-..."` | OpenAI API Key。仅 `whisper_mode` 为 `"api"` 时需要。 |
| `whisper_model` | `"tiny"` / `"base"` / `"small"` / `"medium"` / `"large"` | 本地 Whisper 模型大小。`"base"` 是速度和准确度的平衡选择。 |
| `language` | `"zh"` / `"en"` / `"ja"` / ... | Whisper 语言提示。使用 [ISO 639-1 编码](https://zh.wikipedia.org/wiki/ISO_639-1)。 |
| `extract_frames` | `true` / `false` | 是否提取关键帧截图。默认 `true`。 |
| `frames_per_video` | `1` ~ `20` | 每个视频提取几张截图。默认 `6`。 |
| `cache_ttl_days` | `0` ~ `365` | 缓存结果和截图保留天数。默认 `7` 天。设为 `0` 表示永久保留。 |

### 切换 Whisper 模式

**启用本地 Whisper**（免费，在本机运行）：
```json
{
    "whisper_mode": "local",
    "whisper_model": "base",
    "language": "zh"
}
```
首次运行会下载模型（`base` 约 150MB）。模型大小按质量排序：`tiny` < `base` < `small` < `medium` < `large`（最大约 3GB）。

**启用 OpenAI Whisper API**（快速，需要 API Key）：
```json
{
    "whisper_mode": "api",
    "openai_api_key": "sk-your-key-here",
    "language": "zh"
}
```

**禁用 Whisper**（仅字幕提取，不使用语音识别）：
```json
{
    "whisper_mode": "disabled"
}
```

## TikTok 及其他平台 Cookie 设置

**B站、抖音、小红书均无需 Cookie，脚本通过直接 API 解析获取视频数据。** TikTok 及部分其他平台可能仍需浏览器 Cookie。如果提取失败：

1. 安装浏览器扩展 "[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)"
2. 在浏览器中打开 `douyin.com`（或 `xiaohongshu.com`）— 无需登录
3. 点击扩展图标导出 Cookies
4. 将文件保存为 skill 目录中的 `cookies.txt`

脚本会自动检测名为 `cookies.txt`、`www.douyin.com_cookies.txt` 等的 Cookie 文件。

> **Windows 用户注意**：Chrome 127+ 使用 DPAPI 加密 Cookie，导致 `yt-dlp --cookies-from-browser` 无法读取。建议使用上述手动导出方式。

## 输出格式

提取脚本（`video_subtitle.py`）将 JSON 输出到 stdout：

```json
{
    "title": "视频标题",
    "author": "UP主名称",
    "duration": "05:30",
    "description": "视频描述",
    "platform": "bilibili",
    "url": "https://...",
    "source": "whisper_local",
    "subtitle_text": "完整转录文本...",
    "frames": [
        {"path": "/absolute/path/to/frame_001.jpg", "timestamp": "00:45"},
        {"path": "/absolute/path/to/frame_002.jpg", "timestamp": "01:30"}
    ]
}
```

| 字段 | 说明 |
|---|---|
| `source` | 文本获取方式：`subtitle`（字幕）、`ai_conclusion`（B站AI总结）、`transcript_api`（YouTube字幕API）、`yt_dlp_subs`（yt-dlp字幕）、`whisper_local`（本地Whisper）、`whisper_api`（OpenAI API） |
| `frames` | 关键帧截图数组，包含绝对路径和时间戳。仅在安装了 ffmpeg 且启用 `extract_frames` 时出现。 |
| `error` | 提取失败时的错误信息。成功时不存在此字段。 |

AI 会将 JSON 转换为结构化 Markdown 总结，包含章节标题、亮点、标签和嵌入截图。

## 文件结构

```
multi-video-summarizer/
├── SKILL.md              # Skill 定义文件（触发 AI 发现）
├── video_subtitle.py     # 核心提取脚本（约1500行）
├── config.json           # 用户配置
├── requirements.txt      # pip 依赖清单
├── README.md             # 英文文档
├── README_CN.md          # 中文文档（本文件）
├── INTRODUCE.md          # 项目介绍与文件说明
├── .gitignore            # 排除缓存、截图、Cookie
├── cache/                # （自动创建）缓存的提取结果
└── screenshots/          # （自动创建）关键帧截图
```

## 独立使用

也可以直接在命令行运行脚本：

```bash
python video_subtitle.py "https://www.bilibili.com/video/BV1xxxxxx"
```

输出 JSON 到 stdout。配合 `jq` 快速查看：

```bash
python video_subtitle.py "https://youtu.be/xxxxx" | jq '.title, .source'
```

清除所有缓存结果和截图：

```bash
python video_subtitle.py --clear-cache
```

## 常见问题

| 问题 | 解决方案 |
|---|---|
| "No subtitles or transcript could be extracted" | 在 `config.json` 中启用 Whisper — 很多视频没有内置字幕 |
| YouTube 提取失败（403 错误） | IP 可能被 YouTube 封锁，尝试使用 VPN，或在 Cursor 中使用 WebFetch 工具 |
| 抖音提取失败 | 抖音通常无需 Cookie。如果仍然失败，手动导出 Cookie（参见 [Cookie 设置](#tiktok-及其他平台-cookie-设置)） |
| 小红书提取失败 | 小红书使用直接页面解析（无需 Cookie）。如视频下载失败，请检查网络连接 |
| 找不到 `yt-dlp` | 执行 `pip install yt-dlp`；如果已安装但不在 PATH 中，脚本会自动尝试 `python -m yt_dlp` |
| 找不到 ffmpeg / 没有截图 | 安装 ffmpeg（参见 [安装 ffmpeg](#安装-ffmpeg)）。截图功能是可选的，未安装时会自动跳过 |
| Whisper 模型下载卡住 | 检查网络连接。本地模型首次使用时从 Hugging Face 下载 |
| 缓存结果过时/不准确 | 缓存默认 7 天过期（可通过 `cache_ttl_days` 配置）。手动清除：`python video_subtitle.py --clear-cache` |

## 许可证

MIT
