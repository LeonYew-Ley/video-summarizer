[English](README.md)

# Social Summarizer

一个 AI Agent Skill：抽取**视频**或**图文**，再写成结构化笔记。适用于 **Cursor IDE** 和 **Claude Code**。GitHub / 本地仓库名仍是 `video-summarizer`；Skill 的 `name` 是 `social-summarizer`。

先跑 `extract_content.py`，再按 JSON 里的 `content_type`（`video` 或 `post`）选模板。不要凭用户口头判断类型。

## 支持的平台

| 平台 | URL 示例 | 类型 | 提取方式 | 额外依赖 |
|---|---|---|---|---|
| **B站** | `bilibili.com/video/BVxxx` | 视频 | 公开 API（WBI 签名） | 无（标准库） |
| **YouTube** | `youtube.com/watch?v=xxx`、`youtu.be/xxx` | 视频 | `youtube-transcript-api` | `pip install youtube-transcript-api` |
| **抖音视频** | `douyin.com/video/`、`v.douyin.com/` | 视频 | 分享页 + yt-dlp / Whisper | 可选 `yt-dlp` |
| **抖音图文** | `douyin.com/note/`、分享 `/note/` | 图文 | 分享页公开 SEO 快照 | 无 |
| **小红书** | `xiaohongshu.com/`、`xhslink.com/` | 视频或图文 | 页面解析 | 图文无额外依赖；视频转写用 Whisper |
| **微信公众号** | `mp.weixin.qq.com/s/` | 图文 | 公开免费文 HTML | 无 |
| **TikTok** | `tiktok.com/@user/video/xxx` | 视频 | yt-dlp | `pip install yt-dlp` |
| **1800+ 其他站** | yt-dlp 支持的任意 URL | 视频 | yt-dlp | `pip install yt-dlp` |

## 功能特性

- **一条脚本、两套流程**：按 URL / 页面数据分流 `video` 与 `post`
- **视频三层降级**：平台 API → yt-dlp 字幕 → Whisper
- **时间轴 cues**：有平台字幕、VTT 或 Whisper 分段时输出 `cues`，章节下写 `> mm:ss – mm:ss`
- **图文**：标题、作者、正文写入 `subtitle_text`，配图下到本地（最多 20 张，必须下齐）
- **小红书下图**：`ci.xiaohongshu.com/{token}`；Live Photo 视频轨不算
- **公众号**：只抽公开免费文；付费 / 验证 / 关注可见硬失败，只出 `error`
- **视频关键帧**（需 ffmpeg）
- **按 URL 哈希缓存**；`--clear-cache` 同时删 `cache/`、`screenshots/`、`images/`

## 快速开始

1. **下载** Skill 到指定目录（参见 [安装](#安装)）
2. **按需安装依赖**（参见 [依赖安装](#依赖安装)）
3. **粘贴链接**（视频或图文）到 Cursor / Claude，AI 会跑脚本并按模板写笔记

## 小红书链接必须带 `xsec_token`

发现页 / 笔记链接**必须带刚复制的 `xsec_token`**。从网页（发现流卡片或已打开的笔记）复制**整段 URL**，例如：

```
https://www.xiaohongshu.com/explore/<笔记ID>?xsec_token=AB...=&xsec_source=pc_feed
```

| 参数 | 要不要带 | 说明 |
|---|---|---|
| `xsec_token` | **必须** | 这一次打开/分享的访问凭证。过期或手拼的 token 常 404、`error_code=300031` 或「该内容暂时无法查看」。脚本不会自己生成。 |
| `xsec_source` | 有就留着 | 来源标记（发现页一般是 `pc_feed`）。单独缺了偶尔还能开，复制时不要自己删参数。 |

怎么拿：打开 [小红书发现页](https://www.xiaohongshu.com/explore)，点开笔记或复制卡片链接，把整段地址贴给脚本。分享口令 / `xhslink.com` 可以跟跳转，落到笔记页时仍然需要有效 token。

## 安装

本 Skill **不是** pip 包。把整个文件夹放到 skills 目录即可。

### Cursor IDE

```bash
git clone https://github.com/LeonYew-Ley/video-summarizer.git \
    ~/.cursor/skills/social-summarizer
```

或解压 ZIP 到 `~/.cursor/skills/social-summarizer/`。

**Windows 路径**：`%USERPROFILE%\.cursor\skills\social-summarizer\`

### Claude Code / Claude Desktop

```bash
git clone https://github.com/LeonYew-Ley/video-summarizer.git \
    ~/.claude/skills/social-summarizer
```

**Windows 路径**：`%USERPROFILE%\.claude\skills\social-summarizer\`

### AI 如何发现此 Skill

扫描含 `SKILL.md` 的目录。触发包括平台 URL，以及「总结视频」「总结图文」「总结笔记」「总结帖子」「总结公众号」。AI 先跑 `extract_content.py`，再按 `content_type` 套模板。

## 依赖安装

在**正常 Python 环境**里按需安装，不要只装在 skill 目录里。

### 必需

- **Python 3.8+** — `python --version`

### 按平台

| 用途 | 安装命令 |
|---|---|
| B站视频 | 无需额外依赖 |
| YouTube 视频 | `pip install youtube-transcript-api` |
| 抖音 / 小红书 / 公众号图文 | 元数据与下图无需额外依赖 |
| 抖音 / 小红书视频转写 | Whisper 或 yt-dlp |
| TikTok / 其他站 | `pip install yt-dlp` |

### 可选：Whisper

| 模式 | 安装命令 | 说明 |
|---|---|---|
| 本地 | `pip install faster-whisper` | 首次下载模型约 150MB～3GB |
| OpenAI API | `pip install openai` | 需 Key，约 $0.006/分钟 |
| 音频分割 | `pip install pydub` | API 上传限制 |

### 可选：关键帧

安装 ffmpeg（见下）。Pillow 可选。

```bash
pip install youtube-transcript-api yt-dlp faster-whisper openai pydub Pillow
```

**Windows：** `winget install ffmpeg`  
**macOS：** `brew install ffmpeg`  
**Linux：** `sudo apt install ffmpeg`

## 配置

编辑 skill 目录中的 `config.json`，字段含义与英文 README 相同。`cache_ttl_days` 同时作用于缓存、截图和图文配图。

## Cookie（TikTok 和部分视频）

**B站、公开公众号、多数小红书/抖音图文不需要 Cookie。** TikTok 和部分视频下载可能需要。用扩展导出 `cookies.txt` 放到 skill 目录。也认 `www.douyin.com_cookies.txt` 等文件名。

详见 [小红书链接必须带 `xsec_token`](#小红书链接必须带-xsec_token)。

Windows Chrome 127+ 的 DPAPI 常导致 `--cookies-from-browser` 失败，请手动导出。

## 输出格式

脚本向 stdout 打 JSON。`content_type` 只有 `video` 和 `post`。

视频可带 `cues`（秒）和 `frames`。图文带 `images`；超过 20 张时标 `images_truncated` 和原张数。失败时只有明确的 `error`（付费/验证页不抽正文）。

AI 再写成 Markdown：视频每章标题下 `> mm:ss – mm:ss`（无时间信息才写 `> 无时间轴`）；图文用单独模板，按图序嵌本地图。

## 文件结构

```
social-summarizer/
├── SKILL.md
├── extract_content.py
├── config.json
├── requirements.txt
├── README.md / README_CN.md / INTRODUCE.md
├── .gitignore          # 含 cache/ screenshots/ images/
├── cache/
├── screenshots/
└── images/
```

## 独立使用

```bash
python extract_content.py "https://www.bilibili.com/video/BV1xxxxxx"
python extract_content.py "https://mp.weixin.qq.com/s/xxxxxxxx"
python extract_content.py --clear-cache
```

## 常见问题

| 问题 | 处理 |
|---|---|
| 抽不到字幕 | 在 `config.json` 启用 Whisper |
| YouTube 403 | 换网络 / VPN |
| 抖音图文失败 | `/note/` 必须走图文；分享页无 `item_list` 时走公开 SEO 快照 |
| 小红书打不开 | 换带新 `xsec_token` 的分享/发现页链接 |
| 公众号只有 error | 付费、关注可见、验证码或环境异常，属预期硬失败 |
| 缓存过期 | `python extract_content.py --clear-cache` |

## 许可证

MIT
