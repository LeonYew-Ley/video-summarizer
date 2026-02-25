# Multi-Video-Summarizer 项目介绍

## 这是什么

Multi-Video-Summarizer 是一个 **AI Agent Skill**（AI 代理技能），用于 Cursor IDE 和 Claude Code。当你在对话中粘贴一个视频链接（B站、YouTube、抖音等），AI 会自动识别并调用这个技能，提取视频字幕/转录文本，然后生成带有截图的结构化笔记。

## 工作原理

```
用户粘贴视频链接
       |
       v
AI 读取 SKILL.md，识别到这是视频总结任务
       |
       v
AI 调用 video_subtitle.py 提取字幕
       |
       v
   ┌───────────────────────────────────────────┐
   │          三层提取策略（自动降级）            │
   │                                           │
   │  1. 平台专属 API（B站公开API / YouTube字幕） │
   │            |（失败则继续）                   │
   │  2. yt-dlp 字幕提取（通用方案）             │
   │            |（失败则继续）                   │
   │  3. Whisper 语音识别（下载音频后转文字）     │
   └───────────────────────────────────────────┘
       |
       v
   同时下载低画质视频 → ffmpeg 提取关键帧截图
       |
       v
   输出 JSON（标题、作者、字幕文本、截图路径）
       |
       v
   AI 根据 SKILL.md 中的模板生成 BibiGPT 风格的 Markdown 笔记
```

## 文件说明

### 核心文件

| 文件 | 大小 | 作用 |
|---|---|---|
| `SKILL.md` | ~9KB | **技能入口文件**。Cursor/Claude 通过扫描此文件发现技能。包含触发条件（哪些 URL 模式会激活）、工作流程（调用脚本的命令）、输出模板（BibiGPT 风格的 Markdown 格式）。这是 AI "看到的说明书"。 |
| `video_subtitle.py` | ~60KB | **核心提取脚本**（约1700行）。负责：平台检测（URL → bilibili/youtube/douyin/xiaohongshu/...）、B站公开 API 调用（含 WBI 签名）、YouTube 字幕 API、抖音分享页解析和直接下载、**小红书移动端页面解析和视频直接下载**（从 `__SETUP_SERVER_STATE__` 提取元数据和 CDN 视频地址）、yt-dlp 通用字幕提取、Whisper 语音识别（本地/API）、ffmpeg 关键帧提取、结果缓存。输出 JSON 到 stdout。 |
| `config.json` | ~335B | **用户配置文件**。控制 Whisper 模式（`disabled`/`local`/`api`）、OpenAI API Key、Whisper 模型大小、语言、是否提取截图、每个视频截图数量。用户根据需要修改。 |
| `requirements.txt` | ~800B | **依赖清单**。列出所有可选的 pip 包。不会自动安装，用户按需安装。B站视频不需要任何额外依赖。 |

### 文档文件

| 文件 | 作用 |
|---|---|
| `README.md` | 英文版使用文档。包含安装、配置、依赖、故障排查等完整说明。面向 GitHub 开源。 |
| `README_CN.md` | 中文版使用文档。内容与 README.md 相同。 |
| `INTRODUCE.md` | 本文件。项目架构和文件说明。 |

### 配置文件

| 文件 | 作用 |
|---|---|
| `.gitignore` | 排除运行时产物：`cache/`（缓存）、`screenshots/`（截图）、`__pycache__/`、Cookie 文件、`.bak` 备份文件。确保 Git 仓库只包含源代码。 |

### 自动生成的目录（运行时创建，不入 Git）

| 目录 | 内容 | 说明 |
|---|---|---|
| `cache/` | `<url_hash>.json` | 缓存提取结果。以视频 URL 的哈希值为文件名，存储标题、作者、字幕文本、提取方式等。下次请求同一视频时直接读取缓存，无需重新下载。**默认 7 天过期**（通过 `cache_ttl_days` 配置）。 |
| `screenshots/` | `<url_hash>/frame_001.jpg` ... | 关键帧截图。每个视频一个子目录，包含 N 张均匀分布的 JPEG 截图（默认6张）。**与缓存同步过期**。可通过 `python video_subtitle.py --clear-cache` 手动清除全部缓存和截图。 |
| `__pycache__/` | `.pyc` 文件 | Python 字节码缓存，自动生成，无需关注。 |

## config.json 字段详解

```json
{
    "whisper_mode": "disabled",   // "disabled"=仅字幕 | "local"=本地Whisper | "api"=OpenAI API
    "openai_api_key": "",         // OpenAI API Key，仅 api 模式需要
    "whisper_model": "base",      // 本地模型大小：tiny < base < small < medium < large
    "language": "zh",             // 语音识别语言提示（ISO 639-1）
    "extract_frames": true,       // 是否提取关键帧截图
    "frames_per_video": 6,        // 每个视频提取几张截图
    "cache_ttl_days": 7           // 缓存保留天数，0=永久。过期后自动重新提取
}
```

## 依赖关系一览

```
只看B站视频？        → 无需安装任何依赖
要看YouTube？        → pip install youtube-transcript-api
要看抖音？           → 无需额外依赖（直接 API 解析）
要看小红书？         → 无需额外依赖（直接页面解析 + CDN 下载）
要看TikTok/其他？    → pip install yt-dlp
视频没字幕？         → pip install faster-whisper（本地）
                      或 pip install openai（API，需要Key）
要截图功能？         → 安装 ffmpeg + pip install Pillow
全部都要？           → pip install youtube-transcript-api yt-dlp faster-whisper openai pydub Pillow
```

## 提取策略详解

### B站（Bilibili）

使用公开 API，无需登录或 Cookie：
1. 通过 WBI 签名的 Player V2 API 获取字幕
2. 页面 HTML 中嵌入的字幕信息
3. B站 AI 总结接口

### YouTube

1. `youtube-transcript-api` 库获取字幕轨道
2. yt-dlp 字幕提取
3. Whisper 语音识别（需配置）

### 抖音（Douyin）

1. 解析 `iesdouyin.com/share` 移动端页面，提取视频元数据和直接下载链接
2. 自动生成必要的 Cookie（`s_v_web_id`、`ttwid`）
3. 直接下载视频用于 Whisper 转录

### 小红书（Xiaohongshu）

1. 使用移动端 UA 请求分享页，跟随 `xhslink.com` 短链重定向
2. 从页面 `window.__SETUP_SERVER_STATE__` 解析笔记数据（标题、描述、作者、时长）
3. 从 `media.stream` 中提取视频 CDN 直链（h264/h265 masterUrl），直接下载 MP4
4. 下载视频后用于 Whisper 转录和 ffmpeg 关键帧提取
5. **全程无需 Cookie 或登录**

### 其他平台

统一通过 yt-dlp 处理，支持 1800+ 网站。

## 输出示例

脚本输出 JSON，AI 将其转换为如下 Markdown 笔记：

```markdown
# AI 一键总结：[视频标题](视频链接)

### 🏷️ 章节标题
![章节标题](截图路径)
- 要点1
- 要点2

### 💡 章节标题
![章节标题](截图路径)
- 要点3
- 要点4

### Summary
- 全文摘要

### Highlights
*   🧠 亮点1 [#标签1] [#标签2]
*   🎯 亮点2 [#标签1] [#标签2]

### Questions
*   延伸思考问题1
*   延伸思考问题2
```
