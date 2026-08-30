# Social Summarizer 项目介绍

## 这是什么

Social Summarizer 是一个 **AI Agent Skill**，给 Cursor / Claude Code 用。仓库目录名仍是 `video-summarizer`，Skill 的 `name` 是 `social-summarizer`。

用户粘贴视频或图文链接后，AI 先跑本地脚本抽出 JSON，再按 `content_type` 写成笔记。脚本自己不会「写完整笔记」。

## 工作原理

```
用户粘贴链接（视频或图文）
       |
       v
AI 读取 SKILL.md
       |
       v
python extract_content.py "<URL>"
       |
       v
   平台 + 页面数据判断类型
       |
   ┌───┴────┐
   v        v
 视频      图文
 API/字幕   正文 + 下图
 yt-dlp     最多 20 张必须下齐
 Whisper
 关键帧
       |
       v
 stdout JSON（content_type = video | post）
       |
       v
 AI 按对应模板写 Markdown 笔记
```

## 文件说明

### 核心文件

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能入口。`name: social-summarizer`。先跑脚本，再按 `content_type` 选视频时间轴模板或图文模板。触发词含总结视频 / 总结图文 / 总结笔记 / 总结帖子 / 总结公众号。 |
| `extract_content.py` | 唯一抽取入口。平台检测、B站 API、YouTube 字幕、抖音分享页/SEO 图文、小红书笔记（视频或图文）、微信公开免费文、yt-dlp、Whisper、ffmpeg 关键帧、按 URL 哈希缓存。 |
| `config.json` | Whisper、截图、缓存天数。 |
| `requirements.txt` | 可选 pip 依赖。B站和图文抽取可以不装。 |

### 文档

| 文件 | 作用 |
|---|---|
| `README.md` | 英文使用说明 |
| `README_CN.md` | 中文使用说明 |
| `INTRODUCE.md` | 本文件 |

### 运行时目录（不入 Git）

| 目录 | 说明 |
|---|---|
| `cache/` | `<url_hash>.json`，默认 7 天过期。图文正文必须写入 `subtitle_text` 才能命中。 |
| `screenshots/` | 视频关键帧 |
| `images/` | 图文配图 `<url_hash>/01.png` … |
| `__pycache__/` | Python 字节码 |

`.gitignore` 排除 `cache/`、`screenshots/`、`images/`、Cookie、`.bak`。

`python extract_content.py --clear-cache` 会同时删掉上述三个数据目录。

## JSON 契约

- `content_type` 只有 `video` 和 `post`
- 视频保留旧字段；有时间信息时额外输出 `cues: [{start, end, text}]`（秒）
- 图文：`title` / `author` / `description` / `platform` / `url` / `source` / `subtitle_text` / `images`
- 图文 `platform`：`xiaohongshu` | `douyin` | `weixin`
- 视频 `platform`：`bilibili` | `youtube` | `douyin` | `xiaohongshu` | `tiktok` | `generic`
- 超过 20 张图：`images_truncated: true` 并带原张数；前 20 张必须下齐

## 类型判断

以页面数据为准：

- **小红书**：`type == video` 或有 `play_url` → 视频；否则图文。下图用 `sns-webpic-qc` token 拼 `ci.xiaohongshu.com`
- **抖音**：`/note/`、`images` 非空、或 `aweme_type` 为 68/2 → 图文。分享页若不再内嵌 `item_list`，改读公开 SEO 快照里的 `aweme_images`
- **微信**：`mp.weixin.qq.com` → 图文。`is_pay_subscribe: '1'`、付费阅读、关注可见、验证码、环境异常 → `error`。免费文里也可能出现 `pay_subscribe_info` 且值为 `'0'`，不能据此误杀
- **B站 / YouTube / TikTok / generic** → 视频

## 提取策略

### B站

公开 API，无需登录：Player V2 字幕、页内字幕、AI 总结。

### YouTube

`youtube-transcript-api` → yt-dlp → Whisper。官方字幕或 Whisper 分段都会进 `cues`。

### 抖音

- 图文：`iesdouyin.com/share/note/{id}`；SSR 空壳时用公开 SEO 页拿标题、作者和图片
- 视频：分享页 `play_url`、yt-dlp、Whisper。`/video/` 不得误走图文

### 小红书

- 跟随 `xhslink.com` 的 `Location`（不自动跟跳）
- `__SETUP_SERVER_STATE__` 优先，否则 `__INITIAL_STATE__` → `note.noteDetailMap`
- 图文下图：token → `https://ci.xiaohongshu.com/{token}?imageView2/2/w/0/format/png`；失败再退 `urlDefault` / `urlPre`
- 探索页 / 笔记链接必须带刚从网页复制的 `xsec_token`；`xsec_source` 有就原样保留。过期 token 会 404 / 300031

### 微信公众号

`#activity-name` / og:title，`#js_name`，`#js_content` 正文与 `data-src` 配图。只抽公开免费文。

### 其他

yt-dlp，1800+ 站点。

## 笔记模板（Agent 层）

视频：章节标题下一行引用时间轴。

```markdown
### 主题标题
> 03:12 – 07:45
- 要点
```

无 `cues`（没有带时间的字幕，且 Whisper 也没分段）时写 `> 无时间轴` 并说明原因。

图文：标题+链接+作者；原文要点；按图序嵌本地图；Summary / Highlights / Questions。不写时间戳，不按口播假设。
