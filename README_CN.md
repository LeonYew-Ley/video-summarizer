[English](README.md)

# Social Summarizer

一个给 Cursor 和 Claude Code 使用的 AI Agent Skill：粘贴视频或图文链接，Agent 会抽取内容并写成结构化笔记。

支持字幕获取、Whisper 转写、视频关键帧、图文配图和按 URL 缓存。仓库与 Skill 的名称都是 `social-summarizer`。

## 支持的平台

| 平台 | 类型 | 额外依赖或限制 |
|---|---|---|
| B站 | 视频 | 无 |
| YouTube | 视频 | `youtube-transcript-api` |
| 抖音 | 视频、图文 | 视频可能需要 `yt-dlp` 或 Whisper |
| 小红书 | 视频、图文 | 链接须带有效的 `xsec_token`；视频转写需要 Whisper |
| 微信公众号 | 图文 | 仅支持公开免费文章 |
| TikTok | 视频 | `yt-dlp` |
| yt-dlp 支持的其他站点 | 视频 | `yt-dlp` |

## 安装与使用

本 Skill 不是 pip 包。把下面整段复制给当前环境的 Agent：

```text
请把 Social Summarizer 安装为我的用户级 Agent Skill。

仓库：https://github.com/LeonYew-Ley/social-summarizer
Skill 名：social-summarizer

要求：
1. 按当前环境的用户级 skills 目录安装（这不是 pip 包）。
2. 直接 clone 即可，目录名应是 social-summarizer；根目录下必须有 SKILL.md 和 extract_content.py。
3. 安装后告诉我最终路径，并列出当前平台仍缺少的依赖。
```

安装后，把支持的链接贴给 Cursor 或 Claude 即可。Agent 会运行抽取脚本并按内容类型写笔记。

如果想在终端直接获取 JSON：

```bash
python extract_content.py "https://example.com/video-or-post"
```

清除缓存、视频关键帧和图文配图：

```bash
python extract_content.py --clear-cache
```

## 依赖与配置

需要 Python 3.8+。其他依赖按需安装：

| 用途 | 安装或准备 |
|---|---|
| YouTube 字幕 | `pip install youtube-transcript-api` |
| TikTok、其他站点或部分视频下载 | `pip install yt-dlp` |
| 本地 Whisper | `pip install faster-whisper` |
| OpenAI Whisper API | `pip install openai`；长音频可再装 `pydub` |
| 视频关键帧 | 安装 ffmpeg；`pip install Pillow` 可选 |

ffmpeg 安装命令：Windows `winget install ffmpeg`，macOS `brew install ffmpeg`，Ubuntu/Debian `sudo apt install ffmpeg`。

`config.json` 是可选配置，默认即可使用。常用字段：

| 字段 | 说明 |
|---|---|
| `whisper_mode` | `disabled`、`local` 或 `api` |
| `openai_api_key` | 仅 API 模式需要 |
| `whisper_model` | 本地模型，默认 `base` |
| `language` | Whisper 语言提示，默认 `zh` |
| `extract_frames` | 是否抽取视频关键帧 |
| `frames_per_video` | 关键帧数量，默认 6 |
| `cache_ttl_days` | 缓存有效期；`0` 表示永不过期 |

## 常见问题

### 小红书打不开 / 404 / 300031

发现页或笔记链接必须带刚从网页复制的 `xsec_token`：

```text
https://www.xiaohongshu.com/explore/<笔记ID>?xsec_token=AB...=&xsec_source=pc_feed
```

- 不要手动拼接或删除 `xsec_token`；过期 token 通常会导致 404 或 `error_code=300031`。
- `xsec_source` 有就保留。短链可以跟随跳转，但最终页面仍需要有效 token。

### 要不要 Cookie

B站、公开公众号和多数抖音、小红书图文不需要 Cookie。TikTok 和部分视频下载失败时，可用 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 导出 `cookies.txt`，放到 Skill 根目录。

脚本也识别 `www.douyin.com_cookies.txt`、`www.xiaohongshu.com_cookies.txt` 和 `www.tiktok.com_cookies.txt`。Windows Chrome 127+ 可能阻止 `yt-dlp --cookies-from-browser`，建议直接导出文件。

### 其他问题

| 问题 | 处理 |
|---|---|
| 抽不到字幕 | 在 `config.json` 启用 Whisper |
| YouTube 403 | 重试或更换网络；当前 IP 可能被限制 |
| 抖音视频失败 | 导出 Cookie 或启用 Whisper |
| 公众号返回 `error` | 付费、关注可见、验证码或环境检查不受支持 |
| 找不到 `yt-dlp` | 运行 `pip install yt-dlp` |
| 没有视频关键帧 | 安装 ffmpeg |
| 命中旧缓存 | 运行 `python extract_content.py --clear-cache` |

工作流程、类型判断和 JSON 契约见 [INTRODUCE.md](INTRODUCE.md)。

## 许可证

MIT
