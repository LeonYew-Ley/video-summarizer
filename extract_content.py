#!/usr/bin/env python3
"""
Social Summarizer content extractor.
Extracts video transcripts or image-text posts for AI summarization.

Supported platforms:
  - Bilibili (public API with WBI signing)
  - YouTube (youtube-transcript-api or yt-dlp)
  - Douyin / TikTok (yt-dlp)
  - Xiaohongshu (page parse / yt-dlp)
  - Any yt-dlp supported site (1800+ sites)

Video fallback chain:
  1. Platform-specific subtitle API (free, no auth)
  2. yt-dlp subtitle extraction
  3. yt-dlp audio download + Whisper ASR (local or API)
"""

import glob
import gzip
import hashlib
import html as html_lib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from functools import reduce
from html.parser import HTMLParser

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
CACHE_DIR = os.path.join(SCRIPT_DIR, "cache")
SCREENSHOTS_DIR = os.path.join(SCRIPT_DIR, "screenshots")
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")
COOKIES_PATHS = [
    os.path.join(SCRIPT_DIR, "cookies.txt"),
    os.path.join(SCRIPT_DIR, "www.douyin.com_cookies.txt"),
    os.path.join(SCRIPT_DIR, "www.xiaohongshu.com_cookies.txt"),
    os.path.join(SCRIPT_DIR, "www.tiktok.com_cookies.txt"),
]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


# ---------------------------------------------------------------------------
# Result cache (avoids re-downloading audio / re-running Whisper)
# ---------------------------------------------------------------------------

def _cache_key(url):
    """Normalize URL and produce a stable hash for caching."""
    normalized = re.sub(r'[?&](vd_source|spm_id_from|from|seid)=[^&]*', '', url)
    normalized = normalized.rstrip('/?')
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _normalize_input_url(raw):
    """Pull the first http(s) URL out of share text / 口令."""
    if not raw:
        return raw
    match = re.search(r"https?://[^\s<>\"'，]+", raw)
    if match:
        return match.group(0).rstrip(".,;)]）")
    return raw.strip()


def _cacheable(result):
    if not result or result.get("error"):
        return False
    if result.get("subtitle_text"):
        return True
    return result.get("content_type") == "post" and bool(result.get("images"))


def _read_cache(url):
    key = _cache_key(url)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        ttl_days = load_config().get("cache_ttl_days", 7)
        if ttl_days > 0:
            age_days = (time.time() - os.path.getmtime(path)) / 86400
            if age_days > ttl_days:
                log(f"Cache expired ({age_days:.1f}d > {ttl_days}d): {key}")
                return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if _cacheable(data):
                log(f"Cache hit: {key}")
                data["_cached"] = True
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return None


def _write_cache(url, result):
    """Cache a successful extraction result."""
    if not _cacheable(result):
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _cache_key(url)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log(f"Cached result: {key}")
    except IOError as e:
        log(f"Failed to write cache: {e}", "WARN")


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

PLATFORM_PATTERNS = [
    ("bilibili", [
        r"bilibili\.com/video/",
        r"b23\.tv/",
        r"^BV[a-zA-Z0-9]+$",
    ]),
    ("youtube", [
        r"youtube\.com/watch",
        r"youtube\.com/shorts/",
        r"youtu\.be/",
        r"youtube\.com/live/",
    ]),
    ("douyin", [
        r"douyin\.com/",
        r"v\.douyin\.com/",
        r"iesdouyin\.com/",
    ]),
    ("xiaohongshu", [
        r"xiaohongshu\.com/",
        r"xhslink\.com/",
    ]),
    ("tiktok", [
        r"tiktok\.com/",
    ]),
    ("weixin", [
        r"mp\.weixin\.qq\.com/",
    ]),
]


def detect_platform(url):
    for platform, patterns in PLATFORM_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, url):
                return platform
    return "generic"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def http_get(url, headers=None, raw_bytes=False):
    hdrs = dict(DEFAULT_HEADERS)
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
        if data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)
        if raw_bytes:
            return data
        return data.decode("utf-8")


def api_request(url, params=None, headers=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        text = http_get(url, headers)
        return json.loads(text)
    except urllib.error.HTTPError as e:
        log(f"HTTP {e.code}: {url}", "ERROR")
    except urllib.error.URLError as e:
        log(f"URL error: {e.reason}", "ERROR")
    except Exception as e:
        log(f"Request failed: {e}", "ERROR")
    return None


def log(msg, level="INFO"):
    print(f"[{level}] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Bilibili extractor (public API, no cookies)
# ---------------------------------------------------------------------------

BILI_HEADERS = {
    **DEFAULT_HEADERS,
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
    # Guest device id only — not a login cookie. Avoids some 412s on page fetch.
    "Cookie": f"buvid3={str(uuid.uuid4()).upper()}infoc; b_nut={int(time.time())}",
}

API_VIDEO_VIEW = "https://api.bilibili.com/x/web-interface/view"
API_PLAYER_V2 = "https://api.bilibili.com/x/player/wbi/v2"
API_PLAYURL = "https://api.bilibili.com/x/player/playurl"
API_NAV = "https://api.bilibili.com/x/web-interface/nav"
API_CONCLUSION = "https://api.bilibili.com/x/web-interface/view/conclusion/get"

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(orig):
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, "")[:32]


def _get_wbi_keys():
    try:
        data = api_request(API_NAV, headers=BILI_HEADERS)
        if data and data.get("code") == 0:
            wbi_img = data["data"]["wbi_img"]
            img_key = wbi_img["img_url"].rsplit("/", 1)[1].split(".")[0]
            sub_key = wbi_img["sub_url"].rsplit("/", 1)[1].split(".")[0]
            return img_key, sub_key
    except Exception as e:
        log(f"Failed to get WBI keys: {e}", "WARN")
    return None, None


def _sign_wbi(params, img_key, sub_key):
    mixin_key = _get_mixin_key(img_key + sub_key)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    params = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def _extract_bvid(url_or_bvid):
    if re.match(r"^BV[a-zA-Z0-9]+$", url_or_bvid):
        return url_or_bvid
    for pattern in [
        r"bilibili\.com/video/(BV[a-zA-Z0-9]+)",
        r"b23\.tv/(BV[a-zA-Z0-9]+)",
        r"(BV[a-zA-Z0-9]{10})",
    ]:
        match = re.search(pattern, url_or_bvid)
        if match:
            return match.group(1)
    return None


def _make_cue(start, end, text):
    """Build a timed cue dict. start/end are seconds. Returns None if unusable."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        start = float(start)
        end = float(end) if end is not None else start
    except (TypeError, ValueError):
        return None
    if end < start:
        end = start
    return {"start": round(start, 3), "end": round(end, 3), "text": text}


def _timestamp_to_seconds(value):
    """Parse VTT/SRT timestamps like 00:01:02.500 or 01:02,500 into seconds."""
    if value is None:
        return None
    value = str(value).strip().replace(",", ".")
    value = re.split(r"\s+", value, maxsplit=1)[0]
    parts = value.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 1:
            return float(parts[0])
    except (TypeError, ValueError):
        return None
    return None


def _cues_from_segments(segments, time_offset=0.0):
    """Normalize Whisper/API segment objects into (text, cues)."""
    lines = []
    cues = []
    for seg in segments or []:
        if isinstance(seg, dict):
            text = (seg.get("text") or "").strip()
            start = seg.get("start", 0)
            end = seg.get("end", start)
        else:
            text = (getattr(seg, "text", "") or "").strip()
            start = getattr(seg, "start", 0)
            end = getattr(seg, "end", start)
        if not text:
            continue
        lines.append(text)
        cue = _make_cue(float(start) + time_offset, float(end) + time_offset, text)
        if cue:
            cues.append(cue)
    if not lines:
        return None, []
    return "\n".join(lines), cues


def _bili_parse_subtitle_list(subtitles):
    urls = []
    for sub in subtitles:
        sub_url = sub.get("subtitle_url", "")
        if sub_url:
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url
            urls.append({
                "url": sub_url,
                "lang": sub.get("lan", "unknown"),
                "lang_doc": sub.get("lan_doc", "unknown"),
            })
    return urls


def _bili_download_subtitle(url):
    """Return (text, cues) from a Bilibili subtitle JSON URL."""
    try:
        text = http_get(url, headers=BILI_HEADERS)
        data = json.loads(text)
        body = data.get("body", [])
        if not body:
            return None, []
        lines = []
        cues = []
        for item in body:
            content = (item.get("content") or "").strip()
            if not content:
                continue
            lines.append(content)
            cue = _make_cue(item.get("from"), item.get("to"), content)
            if cue:
                cues.append(cue)
        if not lines:
            return None, []
        return "\n".join(lines), cues
    except Exception as e:
        log(f"Failed to download subtitle: {e}", "ERROR")
        return None, []


def _bili_play_url(bvid, cid):
    """Guest playurl (low-q mp4). Used for Whisper when yt-dlp hits 412."""
    if not bvid or not cid:
        return None
    params = {
        "bvid": bvid, "cid": cid, "qn": 16, "fnval": 1, "fnver": 0, "fourk": 0,
    }
    img_key, sub_key = _get_wbi_keys()
    if img_key and sub_key:
        params = _sign_wbi(params, img_key, sub_key)
    resp = api_request(API_PLAYURL, params=params, headers=BILI_HEADERS)
    if not resp or resp.get("code") != 0:
        return None
    data = resp.get("data") or {}
    for item in data.get("durl") or []:
        url = item.get("url") or item.get("backup_url")
        if isinstance(url, list):
            url = url[0] if url else None
        if url:
            return url
    dash = data.get("dash") or {}
    for stream in (dash.get("audio") or []) + (dash.get("video") or []):
        url = stream.get("baseUrl") or stream.get("base_url")
        if url:
            return url
    return None


def _download_bili_media(play_url, tmp_dir):
    """Download Bilibili CDN media with guest Referer. Returns path or None."""
    if not play_url:
        return None
    try:
        dest = os.path.join(tmp_dir, "bili_media.mp4")
        req = urllib.request.Request(play_url, headers=BILI_HEADERS)
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            log(f"Downloaded Bilibili media: {os.path.getsize(dest) // 1024}KB")
            return dest
    except Exception as e:
        log(f"Bilibili direct download failed: {e}", "WARN")
    return None


def _bili_pick_and_download(subtitle_urls):
    preferred_langs = ["zh-CN", "zh-Hans", "ai-zh", "zh"]
    for lang in preferred_langs:
        for sub in subtitle_urls:
            if lang in sub["lang"]:
                text, cues = _bili_download_subtitle(sub["url"])
                if text:
                    return text, cues, sub["lang_doc"]
    for sub in subtitle_urls:
        text, cues = _bili_download_subtitle(sub["url"])
        if text:
            return text, cues, sub["lang_doc"]
    return None, [], None


def extract_bilibili(url):
    bvid = _extract_bvid(url)
    if not bvid:
        return None

    data = api_request(API_VIDEO_VIEW, params={"bvid": bvid}, headers=BILI_HEADERS)
    if not data or data.get("code") != 0:
        log(f"Failed to get video info: {data}", "ERROR")
        return None

    video = data["data"]
    info = {
        "title": video.get("title", ""),
        "author": video.get("owner", {}).get("name", ""),
        "duration": video.get("duration", 0),
        "description": video.get("desc", ""),
    }
    cid = video.get("cid")
    aid = video.get("aid")
    mid = video.get("owner", {}).get("mid")
    bvid = video.get("bvid", bvid)

    log(f"Bilibili video: {info['title']} (aid={aid}, cid={cid})")

    if not cid:
        log("Could not find cid", "ERROR")
        return _make_result(info, "bilibili", url, error="Could not find cid for this video")

    # Method 1: subtitle list from view API
    subtitle_urls = _bili_parse_subtitle_list(
        video.get("subtitle", {}).get("list", [])
    )

    # Method 2: player v2 API with WBI signing
    if not subtitle_urls:
        log("Trying player v2 API with WBI signing...")
        params = {"bvid": bvid, "cid": cid}
        img_key, sub_key = _get_wbi_keys()
        if img_key and sub_key:
            params = _sign_wbi(params, img_key, sub_key)
        resp = api_request(API_PLAYER_V2, params=params, headers=BILI_HEADERS)
        if resp and resp.get("code") == 0:
            subtitle_urls = _bili_parse_subtitle_list(
                resp.get("data", {}).get("subtitle", {}).get("subtitles", [])
            )

    # Method 3: page HTML scraping
    if not subtitle_urls:
        log("Trying page HTML scraping...")
        try:
            html = http_get(f"https://www.bilibili.com/video/{bvid}/", headers=BILI_HEADERS)
            for match in re.findall(r'"subtitle_url"\s*:\s*"(//[^"]+)"', html):
                sub_url = "https:" + match
                if not any(u["url"] == sub_url for u in subtitle_urls):
                    subtitle_urls.append({"url": sub_url, "lang": "zh-CN", "lang_doc": "中文（自动生成）"})
            for block in re.findall(r'"subtitles"\s*:\s*\[(\{.*?\})\]', html, re.DOTALL):
                try:
                    for sub in json.loads(f"[{block}]"):
                        sub_url = sub.get("subtitle_url", "")
                        if sub_url:
                            if sub_url.startswith("//"):
                                sub_url = "https:" + sub_url
                            if not any(u["url"] == sub_url for u in subtitle_urls):
                                subtitle_urls.append({
                                    "url": sub_url,
                                    "lang": sub.get("lan", "unknown"),
                                    "lang_doc": sub.get("lan_doc", "unknown"),
                                })
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            log(f"Page scraping failed: {e}", "WARN")

    # Method 4: multi-page video
    if not subtitle_urls:
        pages = video.get("pages", [])
        if len(pages) > 1:
            for page in pages:
                page_cid = page.get("cid")
                if page_cid and page_cid != cid:
                    params = {"bvid": bvid, "cid": page_cid}
                    img_key, sub_key = _get_wbi_keys()
                    if img_key and sub_key:
                        params = _sign_wbi(params, img_key, sub_key)
                    resp = api_request(API_PLAYER_V2, params=params, headers=BILI_HEADERS)
                    if resp and resp.get("code") == 0:
                        subtitle_urls = _bili_parse_subtitle_list(
                            resp.get("data", {}).get("subtitle", {}).get("subtitles", [])
                        )
                        if subtitle_urls:
                            break

    play_url = _bili_play_url(bvid, cid)

    # Download best subtitle
    if subtitle_urls:
        text, cues, lang = _bili_pick_and_download(subtitle_urls)
        if text:
            result = _make_result(info, "bilibili", url, text, "subtitle", cues=cues)
            result["_play_url"] = play_url
            return result

    # Method 5: B站 AI conclusion API
    if aid and cid and mid:
        log("Trying B站 AI conclusion API...")
        params = {"aid": aid, "cid": cid, "up_mid": mid}
        img_key, sub_key = _get_wbi_keys()
        if img_key and sub_key:
            params = _sign_wbi(params, img_key, sub_key)
        resp = api_request(API_CONCLUSION, params=params, headers=BILI_HEADERS)
        if resp and resp.get("code") == 0:
            model_result = resp.get("data", {}).get("model_result", {})
            if model_result:
                parts = []
                summary = model_result.get("summary", "")
                if summary:
                    parts.append(summary)
                for section in model_result.get("outline", []):
                    title = section.get("title", "")
                    if title:
                        parts.append(f"\n## {title}")
                    for kp in section.get("key_point", []):
                        content = kp.get("content", "")
                        if content:
                            parts.append(f"- {content}")
                if parts:
                    result = _make_result(info, "bilibili", url, "\n".join(parts), "ai_conclusion")
                    result["_play_url"] = play_url
                    return result

    result = _make_result(info, "bilibili", url)
    result["_play_url"] = play_url
    return result


# ---------------------------------------------------------------------------
# YouTube extractor
# ---------------------------------------------------------------------------

def _extract_youtube_id(url):
    patterns = [
        r"youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/live/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_youtube(url):
    video_id = _extract_youtube_id(url)
    if not video_id:
        return None

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    info = {"title": "", "author": "", "duration": 0, "description": ""}

    # Try youtube-transcript-api first (lightweight, no deps beyond pip)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        log("Using youtube-transcript-api...")
        try:
            ytt = YouTubeTranscriptApi()
            transcript_list = ytt.list(video_id)
            transcript = None
            for lang in ["zh-Hans", "zh-CN", "zh", "zh-Hant", "en"]:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    break
                except Exception:
                    continue
            if not transcript:
                try:
                    transcript = transcript_list.find_generated_transcript(["zh-Hans", "zh-CN", "zh", "en"])
                except Exception:
                    transcripts = list(transcript_list)
                    if transcripts:
                        transcript = transcripts[0]

            if transcript:
                fetched = transcript.fetch()
                lines = []
                cues = []
                for entry in fetched:
                    if isinstance(entry, dict):
                        text_line = (entry.get("text") or "").strip()
                        start = entry.get("start", 0)
                        duration = entry.get("duration", 0) or 0
                    elif hasattr(entry, "text"):
                        text_line = (entry.text or "").strip()
                        start = getattr(entry, "start", 0)
                        duration = getattr(entry, "duration", 0) or 0
                    else:
                        text_line = str(entry).strip()
                        start = None
                        duration = 0
                    if not text_line:
                        continue
                    lines.append(text_line)
                    if start is not None:
                        cue = _make_cue(start, float(start) + float(duration), text_line)
                        if cue:
                            cues.append(cue)
                text = "\n".join(lines)
                if text:
                    _fill_youtube_info(info, video_id)
                    return _make_result(info, "youtube", canonical_url, text, "transcript_api", cues=cues)
        except Exception as e:
            log(f"youtube-transcript-api failed: {e}", "WARN")
    except ImportError:
        log("youtube-transcript-api not installed, will try yt-dlp", "WARN")

    _fill_youtube_info(info, video_id)
    return _make_result(info, "youtube", canonical_url)


def _fill_youtube_info(info, video_id):
    """Best-effort fill of YouTube video metadata via oembed (no API key needed)."""
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        data = json.loads(http_get(oembed_url))
        info["title"] = data.get("title", "")
        info["author"] = data.get("author_name", "")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Douyin extractor (fetches page HTML to extract video description)
# ---------------------------------------------------------------------------

DOUYIN_HEADERS = {
    **DEFAULT_HEADERS,
    "Referer": "https://www.douyin.com",
    "Cookie": "s_v_web_id=verify_placeholder",
}

DOUYIN_MOBILE_UA = (
    "com.ss.android.ugc.aweme/110101 "
    "(Linux; U; Android 12; en_US; Pixel 6; Build/SD1A.210817.036; "
    "Cronet/TTNetVersion:b4d74d15 2023-04-08)"
)

# Public SEO snapshot of the share page (item_list is no longer in app SSR).
DOUYIN_SEO_UA = (
    "Mozilla/5.0 (compatible; Baiduspider/2.0; "
    "+http://www.baidu.com/search/spider.html)"
)
DOUYIN_SEO_IMAGE_RE = re.compile(
    r"https://p\d+-pc-sign\.douyinpic\.com/"
    r"(tos-cn-i-[^/\"'\s~]+/[^/\"'\s~]+)~tplv-dy-aweme-images[^\"'\s]*",
    re.I,
)

AUTO_COOKIES_PATH = os.path.join(SCRIPT_DIR, "_auto_douyin_cookies.txt")


def _fetch_fresh_douyin_cookies():
    """Generate fresh Douyin cookies (s_v_web_id, ttwid, etc.) required by yt-dlp.
    s_v_web_id is a client-side cookie generated by JS — we synthesize it here.
    ttwid is obtained by hitting douyin.com and collecting the Set-Cookie header.
    Writes Netscape cookie-jar format for yt-dlp. Returns file path or None."""
    import http.cookiejar
    import secrets
    import time as _time

    try:
        cj = http.cookiejar.MozillaCookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj),
        )
        req = urllib.request.Request("https://www.douyin.com/", headers={
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        try:
            opener.open(req, timeout=15).read()
        except Exception:
            pass

        existing_names = {c.name for c in cj}

        if "s_v_web_id" not in existing_names:
            verify_id = f"verify_{secrets.token_hex(16)}"
            cj.set_cookie(http.cookiejar.Cookie(
                version=0, name="s_v_web_id", value=verify_id,
                port=None, port_specified=False,
                domain=".douyin.com", domain_specified=True, domain_initial_dot=True,
                path="/", path_specified=True,
                secure=True, expires=int(_time.time()) + 86400 * 30,
                discard=False, comment=None, comment_url=None,
                rest={"HttpOnly": None},
            ))

        if "ttwid" not in existing_names:
            try:
                ttwid_req = urllib.request.Request(
                    "https://ttwid.bytedance.com/ttwid/union/register/",
                    data=json.dumps({
                        "region": "cn",
                        "aid": 1128,
                        "needFid": False,
                        "service": "www.ixigua.com",
                        "migrate_info": {"ticket": "", "source": "node"},
                        "cbUrlProtocol": "https",
                        "union": True,
                    }).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": DEFAULT_HEADERS["User-Agent"],
                    },
                    method="POST",
                )
                resp = urllib.request.urlopen(ttwid_req, timeout=10)
                for header_val in resp.headers.get_all("Set-Cookie") or []:
                    if "ttwid=" in header_val:
                        ttwid_val = header_val.split("ttwid=")[1].split(";")[0]
                        cj.set_cookie(http.cookiejar.Cookie(
                            version=0, name="ttwid", value=ttwid_val,
                            port=None, port_specified=False,
                            domain=".douyin.com", domain_specified=True, domain_initial_dot=True,
                            path="/", path_specified=True,
                            secure=True, expires=int(_time.time()) + 86400 * 30,
                            discard=False, comment=None, comment_url=None,
                            rest={"HttpOnly": None},
                        ))
            except Exception as e:
                log(f"ttwid fetch failed (non-fatal): {e}", "WARN")

        cj.save(AUTO_COOKIES_PATH, ignore_discard=True, ignore_expires=True)
        names = [c.name for c in cj]
        log(f"Auto-generated {len(names)} Douyin cookies: {', '.join(names)}")
        return AUTO_COOKIES_PATH
    except Exception as e:
        log(f"Auto-fetch Douyin cookies failed: {e}", "WARN")
        return None


def _match_douyin_id(url):
    patterns = [
        (r"douyin\.com/note/(\d+)", "note"),
        (r"douyin\.com/video/(\d+)", "video"),
        (r"iesdouyin\.com/share/note/(\d+)", "note"),
        (r"iesdouyin\.com/share/video/(\d+)", "video"),
    ]
    for pat, kind in patterns:
        match = re.search(pat, url or "")
        if match:
            return match.group(1), kind
    return None, None


def _resolve_douyin_url(url):
    """Resolve v.douyin.com short link. Returns (aweme_id, resolved_url, kind)."""
    url = _normalize_input_url(url)
    resolved = url
    try:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            resolved = resp.url
    except Exception as e:
        log(f"Failed to resolve Douyin URL: {e}", "WARN")
    aweme_id, kind = _match_douyin_id(resolved)
    if not aweme_id:
        aweme_id, kind = _match_douyin_id(url)
    return aweme_id, resolved, kind


def _loads_embedded_json(raw):
    raw = (raw or "").strip()
    if raw.endswith(";"):
        raw = raw[:-1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"\bundefined\b", "null", raw)
    cleaned = re.sub(r"\bNaN\b", "null", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _parse_script_assignment(html, marker):
    match = re.search(re.escape(marker) + r"\s*=\s*", html or "")
    if not match:
        return None
    json_start = match.end()
    script_end = html.find("</script>", json_start)
    if script_end == -1:
        return None
    return _loads_embedded_json(html[json_start:script_end])


def _find_item_list(obj):
    """Walk nested JSON for a Douyin item_list with aweme/video/images."""
    if isinstance(obj, dict):
        items = obj.get("item_list")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and (
                "aweme_id" in first or "video" in first or "images" in first
                or "image_post_info" in first
            ):
                return first
        for value in obj.values():
            found = _find_item_list(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_item_list(value)
            if found:
                return found
    return None


def _douyin_item_from_share_html(html):
    router_data = _parse_script_assignment(html, "_ROUTER_DATA")
    if router_data:
        item = _find_item_list(router_data)
        if item:
            return item
    render_data = _parse_script_assignment(html, "window._RENDER_DATA")
    if render_data:
        item = _find_item_list(render_data)
        if item:
            return item
    match = re.search(
        r'<script[^>]+id="RENDER_DATA"[^>]*>(.*?)</script>',
        html or "",
        re.I | re.DOTALL,
    )
    if match:
        raw = urllib.parse.unquote(match.group(1).strip())
        decoded = _loads_embedded_json(raw)
        if decoded:
            return _find_item_list(decoded)
    return None


def _douyin_payload_from_seo_html(html):
    """Parse title, author, and aweme_images from the public SEO share page."""
    if not html:
        return None
    title = _weixin_meta(html, r"<title[^>]*>(.*?)</title>")
    title = re.sub(r"\s+", " ", title).replace(" - 抖音", "").strip()
    description = _weixin_meta(html, r'name="description"\s+content="([^"]*)"')
    description = html_lib.unescape(description).strip()
    author = ""
    author_match = re.search(r" - ([^于\n]{1,40})于\d{8}发布", description)
    if author_match:
        author = author_match.group(1).strip()
        description = description[: author_match.start()].strip()
    seen = {}
    for match in DOUYIN_SEO_IMAGE_RE.finditer(html.replace("&amp;", "&")):
        key = match.group(1)
        if key not in seen:
            seen[key] = match.group(0)
    image_urls = list(seen.values())
    if not title and not image_urls:
        return None
    return {
        "info": {
            "title": title,
            "author": author,
            "duration": 0,
            "description": description or title,
        },
        "play_url": None,
        "image_urls": image_urls,
        "aweme_type": 68 if image_urls else None,
        "item": None,
    }


def _douyin_item_payload(item):
    info = {
        "title": item.get("desc", "") or "",
        "author": (item.get("author") or {}).get("nickname", ""),
        "duration": (item.get("video") or {}).get("duration", 0) or 0,
        "description": item.get("desc", "") or "",
    }
    dur = info["duration"]
    if isinstance(dur, (int, float)) and dur > 10000:
        info["duration"] = dur / 1000.0

    play_url = None
    video_obj = item.get("video") or {}
    for addr_key in ("play_addr", "play_addr_h264", "download_addr"):
        addr = video_obj.get(addr_key) or {}
        if isinstance(addr, dict):
            urls = addr.get("url_list") or []
            if urls:
                play_url = urls[0]
                break

    image_urls = []
    seen = set()

    def _add_image_url(url):
        if url and url not in seen:
            seen.add(url)
            image_urls.append(url)

    for img in item.get("images") or []:
        if not isinstance(img, dict):
            continue
        url_list = img.get("url_list") or img.get("download_url_list") or []
        if url_list:
            _add_image_url(url_list[-1])
    post = item.get("image_post_info") or {}
    if isinstance(post, dict):
        for img in post.get("images") or []:
            if isinstance(img, dict):
                url_list = img.get("url_list") or img.get("download_url_list") or []
                if url_list:
                    _add_image_url(url_list[-1])

    return {
        "info": info,
        "play_url": play_url,
        "image_urls": image_urls,
        "aweme_type": item.get("aweme_type"),
        "item": item,
    }


def _douyin_is_post(payload, kind):
    if not payload:
        return False
    if kind == "note":
        return True
    if payload.get("image_urls"):
        return True
    return payload.get("aweme_type") in (2, 68, "2", "68")


def _douyin_share_api(aweme_id, kind=None):
    """Fetch metadata from iesdouyin.com share page. Returns payload dict or None."""
    if kind == "note":
        share_urls = [
            f"https://www.iesdouyin.com/share/note/{aweme_id}/",
            f"https://www.iesdouyin.com/share/video/{aweme_id}/",
        ]
    elif kind == "video":
        share_urls = [f"https://www.iesdouyin.com/share/video/{aweme_id}/"]
    else:
        share_urls = [
            f"https://www.iesdouyin.com/share/video/{aweme_id}/",
            f"https://www.iesdouyin.com/share/note/{aweme_id}/",
        ]

    user_agents = (
        DOUYIN_MOBILE_UA,
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1",
    )
    if kind != "video":
        user_agents = user_agents + (DOUYIN_SEO_UA,)
    for share_url in share_urls:
        for ua in user_agents:
            try:
                req = urllib.request.Request(share_url, headers={
                    "User-Agent": ua,
                    "Accept": "text/html,*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                })
                resp = urllib.request.urlopen(req, timeout=15)
                html = resp.read().decode("utf-8", errors="replace")
                item = _douyin_item_from_share_html(html)
                if item:
                    return _douyin_item_payload(item)
                if ua == DOUYIN_SEO_UA:
                    seo = _douyin_payload_from_seo_html(html)
                    if seo and seo.get("image_urls"):
                        return seo
            except Exception as e:
                log(f"Douyin share API failed ({share_url}): {e}", "WARN")
    return None


def _download_douyin_audio(play_url, tmp_dir):
    """Download Douyin video (as audio source) directly from play_url.
    Returns the saved file path or None."""
    if not play_url:
        return None
    try:
        audio_path = os.path.join(tmp_dir, "douyin_audio.mp4")
        req = urllib.request.Request(play_url, headers={
            "User-Agent": DOUYIN_MOBILE_UA,
            "Referer": "https://www.douyin.com/",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(audio_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
            log(f"Downloaded Douyin video: {os.path.getsize(audio_path) // 1024}KB")
            return audio_path
    except Exception as e:
        log(f"Douyin direct download failed: {e}", "WARN")
    return None



# ---------------------------------------------------------------------------
# Xiaohongshu extractor (direct page parsing, no cookies needed)
# ---------------------------------------------------------------------------

XHS_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
    "Mobile/15E148 Safari/604.1"
)

XHS_DESKTOP_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _follow_location(url, headers, max_hops=5):
    """Read Location like nfe-w (maxRedirects: 0) instead of auto-following."""
    current = url
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(max_hops):
        req = urllib.request.Request(current, headers=headers)
        try:
            with opener.open(req, timeout=15) as resp:
                return resp.url, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            location = e.headers.get("Location")
            if e.code in (301, 302, 303, 307, 308) and location:
                current = urllib.parse.urljoin(current, location)
                continue
            raise
    return current, None


def _resolve_xhs_url(url):
    """Resolve xhslink.com short link and extract note ID."""
    url = _normalize_input_url(url)
    html = None
    resolved = url
    try:
        if re.search(r"xhslink\.com", url):
            resolved, html = _follow_location(url, XHS_DESKTOP_HEADERS)
        if html is None:
            req = urllib.request.Request(url if resolved == url else resolved, headers=XHS_DESKTOP_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                resolved = resp.url
                html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log(f"Failed to resolve XHS URL: {e}", "WARN")
        return None, None, url

    for pat in [
        r"/discovery/item/([a-f0-9]+)",
        r"/explore/([a-f0-9]+)",
        r"/item/([a-f0-9]+)",
        r"noteId[\"=:]\"?([a-f0-9]{24})",
    ]:
        m = re.search(pat, resolved)
        if m:
            return m.group(1), html, resolved

    return None, html, resolved


def _xhs_note_from_setup(html):
    data = _parse_script_assignment(html, "window.__SETUP_SERVER_STATE__")
    if not data:
        return None
    return (data.get("LAUNCHER_SSR_STORE_PAGE_DATA") or {}).get("noteData") or None


def _xhs_note_from_initial(html):
    data = _parse_script_assignment(html, "window.__INITIAL_STATE__")
    if not data:
        return None
    note = data.get("note") or {}
    first_id = note.get("firstNoteId")
    detail_map = note.get("noteDetailMap") or {}
    if first_id and isinstance(detail_map.get(first_id), dict):
        return detail_map[first_id].get("note")
    for value in detail_map.values():
        if isinstance(value, dict) and value.get("note"):
            return value["note"]
    return None


def _parse_xhs_page(html):
    """Parse XHS page HTML for note data and video URLs from __SETUP_SERVER_STATE__."""
    note = _xhs_note_from_html(html)
    if not note:
        return None, None
    return _xhs_info_from_note(note), _xhs_video_play_url(note)


def _xhs_note_from_html(html):
    note = _xhs_note_from_setup(html)
    if note and (note.get("imageList") or _xhs_video_play_url(note) or note.get("title") or note.get("desc")):
        return note
    return _xhs_note_from_initial(html) or note


def _xhs_info_from_note(note):
    user = note.get("user") or {}
    video_obj = note.get("video") or {}
    media = video_obj.get("media") or {}
    capa = video_obj.get("capa") or {}
    vid = media.get("video") or {}
    duration = capa.get("duration") or vid.get("duration", 0) or 0
    if isinstance(duration, (int, float)) and duration > 10000:
        duration = duration / 1000.0
    author = user.get("nickName") or user.get("nickname") or ""
    return {
        "title": note.get("title", "") or "",
        "author": author,
        "duration": duration,
        "description": note.get("desc", "") or "",
    }


def _xhs_video_play_url(note):
    if not note:
        return None
    video_obj = note.get("video") or {}
    media = video_obj.get("media") or {}
    stream = media.get("stream") or {}
    for codec in ("h264", "h265", "av1", "h266"):
        streams = stream.get(codec) or []
        if streams and isinstance(streams, list):
            best = streams[0] or {}
            play_url = best.get("masterUrl")
            if play_url:
                return play_url
            backup = best.get("backupUrls") or []
            if backup:
                return backup[0]
    return None


def _xhs_is_video_note(note):
    ntype = (note.get("type") or "").lower()
    if ntype == "video":
        return True
    return bool(_xhs_video_play_url(note))


def _xhs_image_urls(note):
    """Rewrite imageList to ci.xiaohongshu.com URLs. None means a listed image is unusable."""
    image_list = note.get("imageList") or []
    urls = []
    for item in image_list:
        if not isinstance(item, dict):
            return None
        info_list = item.get("infoList") or []
        info_url = ""
        if info_list and isinstance(info_list[0], dict):
            info_url = info_list[0].get("url") or ""
        token_match = XHS_PIC_TOKEN_RE.search(info_url)
        chosen = None
        if token_match:
            chosen = f"https://ci.xiaohongshu.com/{token_match.group(1)}?imageView2/2/w/0/format/png"
        if not chosen:
            chosen = item.get("urlDefault") or item.get("urlPre") or info_url
        if not chosen:
            return None
        urls.append(chosen)
    return urls


def extract_xiaohongshu(url):
    """Extract Xiaohongshu video or image note via mobile page HTML."""
    note_id, html, resolved_url = _resolve_xhs_url(url)

    blocked = (
        html
        and (
            "/404" in resolved_url
            or "error_code=300031" in html
            or "undertake_note_error" in resolved_url
            or "该内容暂时无法查看" in urllib.parse.unquote(resolved_url)
        )
    )
    if blocked:
        return _make_post_result(
            {"title": "", "author": "", "duration": 0, "description": ""},
            "xiaohongshu",
            resolved_url,
            error="Xiaohongshu note is unavailable or blocked",
        )

    if html:
        note = _xhs_note_from_html(html)
        if note:
            info = _xhs_info_from_note(note)
            log(f"XHS note: {info['title'] or info['description'][:40]} (type={note.get('type')})")
            if not _xhs_is_video_note(note):
                image_urls = _xhs_image_urls(note)
                if image_urls is None:
                    return _make_post_result(
                        info, "xiaohongshu", resolved_url,
                        error="Failed to resolve Xiaohongshu image URLs",
                    )
                return _finalize_post(
                    info,
                    "xiaohongshu",
                    resolved_url,
                    image_urls,
                    referer="https://www.xiaohongshu.com/",
                    user_agent=XHS_MOBILE_UA,
                )
            result = _make_result(info, "xiaohongshu", resolved_url)
            result["_play_url"] = _xhs_video_play_url(note)
            return result

    return _make_result(
        {"title": "", "author": "", "duration": 0, "description": ""},
        "xiaohongshu", resolved_url,
    )


def _download_xhs_video(play_url, tmp_dir):
    """Download XHS video directly from CDN URL. Returns file path or None."""
    if not play_url:
        return None
    try:
        video_path = os.path.join(tmp_dir, "xhs_video.mp4")
        req = urllib.request.Request(play_url, headers={
            "User-Agent": XHS_MOBILE_UA,
            "Referer": "https://www.xiaohongshu.com/",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(video_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        if os.path.exists(video_path) and os.path.getsize(video_path) > 1000:
            log(f"Downloaded XHS video: {os.path.getsize(video_path) // 1024}KB")
            return video_path
    except Exception as e:
        log(f"XHS direct download failed: {e}", "WARN")
    return None


def extract_douyin(url):
    """Extract Douyin video or image-note via the iesdouyin share page."""
    aweme_id, resolved_url, kind = _resolve_douyin_url(url)
    if not aweme_id:
        return None

    payload = _douyin_share_api(aweme_id, kind=kind)
    if kind == "note":
        info = (payload or {}).get("info") or {
            "title": "", "author": "", "duration": 0, "description": "",
        }
        if not payload:
            return _make_post_result(
                info, "douyin", resolved_url,
                error="Could not parse Douyin note page (share page had no embedded item data)",
            )
        return _finalize_post(
            info,
            "douyin",
            resolved_url,
            payload.get("image_urls") or [],
            referer="https://www.douyin.com/",
            user_agent=DOUYIN_MOBILE_UA,
        )

    if not payload:
        info = {"title": "", "author": "", "duration": 0, "description": ""}
        result = _make_result(info, "douyin", resolved_url)
        return result

    info = payload["info"]
    if _douyin_is_post(payload, kind):
        return _finalize_post(
            info,
            "douyin",
            resolved_url,
            payload.get("image_urls") or [],
            referer="https://www.douyin.com/",
            user_agent=DOUYIN_MOBILE_UA,
        )

    result = _make_result(info, "douyin", resolved_url)
    result["_play_url"] = payload.get("play_url")
    return result


# ---------------------------------------------------------------------------
# Weixin public article extractor
# ---------------------------------------------------------------------------

WEIXIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://mp.weixin.qq.com/",
}

WEIXIN_PAYWALL_MARKERS = (
    "is_pay_subscribe: '1'",
    'is_pay_subscribe: "1"',
)
WEIXIN_VERIFY_MARKERS = (
    'id="js_verify"',
    'id="verify_code"',
    "此内容需关注",
    "关注后才能阅读",
    "关注后可查看",
    "关注公众号后阅读",
    "环境异常",
    "完成验证后即可继续访问",
)
# Body copy about the product feature is not a paywall. Only treat
# 「付费阅读」as blocked when the article is not explicitly free.
WEIXIN_PAYWALL_PHRASE = "付费阅读"


class _WeixinContentParser(HTMLParser):
    """Collect visible text and image URLs from #js_content."""

    def __init__(self):
        super().__init__()
        self.in_content = False
        self.depth = 0
        self.parts = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.in_content:
            if attrs.get("id") == "js_content":
                self.in_content = True
                self.depth = 1
            return
        if tag == "div":
            self.depth += 1
        if tag in ("p", "br", "h1", "h2", "h3", "h4", "li", "section"):
            self.parts.append("\n")
        if tag == "img":
            src = attrs.get("data-src") or attrs.get("data-original") or attrs.get("src")
            if src and src.startswith("http"):
                self.images.append(src)

    def handle_endtag(self, tag):
        if self.in_content and tag == "div":
            self.depth -= 1
            if self.depth <= 0:
                self.in_content = False

    def handle_data(self, data):
        if self.in_content:
            text = data.strip()
            if text:
                self.parts.append(text)


def _weixin_blocked_reason(html):
    if not html:
        return "empty page"
    for marker in WEIXIN_PAYWALL_MARKERS:
        if marker in html:
            return marker
    explicitly_free = (
        "is_pay_subscribe: '0'" in html or 'is_pay_subscribe: "0"' in html
    )
    if WEIXIN_PAYWALL_PHRASE in html and not explicitly_free:
        return WEIXIN_PAYWALL_PHRASE
    for marker in WEIXIN_VERIFY_MARKERS:
        if marker in html:
            return marker
    if "js_content" not in html and ("verify" in html.lower() or "captcha" in html.lower()):
        return "verification page"
    return None


def _weixin_meta(html, pattern):
    match = re.search(pattern, html or "", re.I | re.DOTALL)
    if not match:
        return ""
    return html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


def extract_weixin(url):
    """Extract a public free Weixin article. Blocked/paid/verify pages hard-fail."""
    url = _normalize_input_url(url)
    try:
        html = http_get(url, headers=WEIXIN_HEADERS)
    except Exception as e:
        return _make_post_result(
            {"title": "", "author": "", "duration": 0, "description": ""},
            "weixin",
            url,
            error=f"Failed to fetch Weixin article: {e}",
        )

    blocked = _weixin_blocked_reason(html)
    if blocked:
        return _make_post_result(
            {"title": "", "author": "", "duration": 0, "description": ""},
            "weixin",
            url,
            error=f"Weixin article is not publicly readable ({blocked})",
        )

    title = (
        _weixin_meta(html, r'id="activity-name"[^>]*>(.*?)</')
        or _weixin_meta(html, r'property="og:title"\s+content="([^"]+)"')
    )
    author = (
        _weixin_meta(html, r'id="js_name"[^>]*>(.*?)</')
        or _weixin_meta(html, r'id="js_author_name"[^>]*>(.*?)</')
        or _weixin_meta(html, r'property="og:article:author"\s+content="([^"]+)"')
        or _weixin_meta(html, r'id="js_profile_qrcode"[^>]*data-nickname="([^"]+)"')
    )
    parser = _WeixinContentParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    body = re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()
    info = {
        "title": title,
        "author": author,
        "duration": 0,
        "description": body,
    }
    return _finalize_post(
        info,
        "weixin",
        url,
        parser.images,
        referer="https://mp.weixin.qq.com/",
        user_agent=WEIXIN_HEADERS["User-Agent"],
    )


# ---------------------------------------------------------------------------
# yt-dlp based extractor (generic, works for all yt-dlp supported sites)
# ---------------------------------------------------------------------------

PLATFORMS_NEEDING_COOKIES = {"douyin", "xiaohongshu", "tiktok"}


def _get_ytdlp_cmd():
    """Return the command prefix for yt-dlp. Tries the binary first, then python -m."""
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    try:
        subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True, timeout=10,
        )
        return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        return None


def _check_ytdlp():
    return _get_ytdlp_cmd() is not None


def _run_ytdlp(args, timeout=60):
    """Run yt-dlp and return (returncode, stdout_str). Handles Windows encoding.
    args[0] should be 'yt-dlp'; it will be replaced with the correct command."""
    cmd = _get_ytdlp_cmd()
    if cmd is None:
        return 1, "yt-dlp not found"
    actual_args = cmd + list(args[1:])
    result = subprocess.run(
        actual_args, capture_output=True, timeout=timeout,
    )
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    return result.returncode, stdout


def _detect_browser():
    """Detect an available browser for --cookies-from-browser.
    Checks common browser data directories on Windows/Mac/Linux."""
    home = os.path.expanduser("~")
    browser_paths = {
        "chrome": [
            os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data"),
            os.path.join(home, ".config", "google-chrome"),
            os.path.join(home, "Library", "Application Support", "Google", "Chrome"),
        ],
        "edge": [
            os.path.join(home, "AppData", "Local", "Microsoft", "Edge", "User Data"),
        ],
        "firefox": [
            os.path.join(home, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles"),
            os.path.join(home, ".mozilla", "firefox"),
            os.path.join(home, "Library", "Application Support", "Firefox", "Profiles"),
        ],
        "brave": [
            os.path.join(home, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data"),
        ],
    }
    for browser, paths in browser_paths.items():
        for p in paths:
            if os.path.isdir(p):
                return browser
    return None


_cached_browser = None
_cookie_args_tested = False
_cookie_args_result = []


def _get_cookie_args(platform):
    """Return extra yt-dlp args for platforms that need browser cookies.
    Priority: user cookies file > auto-fetched cookies > --cookies-from-browser.
    Tests once whether the chosen method actually works."""
    global _cached_browser, _cookie_args_tested, _cookie_args_result
    if platform not in PLATFORMS_NEEDING_COOKIES:
        return []
    if _cookie_args_tested:
        return _cookie_args_result

    _cookie_args_tested = True

    # Priority 1: user-provided cookies file in skill directory
    for cp in COOKIES_PATHS:
        if os.path.isfile(cp):
            log(f"Using cookies file: {os.path.basename(cp)}")
            _cookie_args_result = ["--cookies", cp]
            return _cookie_args_result
    for f in glob.glob(os.path.join(SCRIPT_DIR, "*cookies*.txt")):
        if os.path.isfile(f) and "_auto_" not in os.path.basename(f):
            log(f"Using cookies file: {os.path.basename(f)}")
            _cookie_args_result = ["--cookies", f]
            return _cookie_args_result

    # Priority 2: auto-fetch fresh cookies from the platform
    if platform == "douyin":
        auto_path = _fetch_fresh_douyin_cookies()
        if auto_path:
            _cookie_args_result = ["--cookies", auto_path]
            return _cookie_args_result

    # Priority 3: --cookies-from-browser
    _cached_browser = _detect_browser() or ""
    if _cached_browser:
        try:
            rc, _ = _run_ytdlp(
                ["yt-dlp", "--cookies-from-browser", _cached_browser,
                 "--dump-json", "--no-download", "https://www.douyin.com/"],
                timeout=15,
            )
            if rc == 0:
                log(f"Using cookies from browser: {_cached_browser}")
                _cookie_args_result = ["--cookies-from-browser", _cached_browser]
                return _cookie_args_result
        except Exception:
            pass
        log(f"Browser cookie extraction failed ({_cached_browser})", "WARN")
    else:
        log("No browser detected for cookie extraction", "WARN")

    return []


def _ytdlp_extract_info(url, platform="generic"):
    """Use yt-dlp --dump-json to get video metadata without downloading."""
    try:
        cmd = ["yt-dlp", "--dump-json", "--no-download", "--no-playlist"]
        cmd += _get_cookie_args(platform)
        cmd.append(url)
        rc, stdout = _run_ytdlp(cmd)
        if rc == 0 and stdout.strip():
            return json.loads(stdout)
    except Exception as e:
        log(f"yt-dlp info extraction failed: {e}", "WARN")
    return None


def _ytdlp_extract_subs(url, tmp_dir, platform="generic"):
    """Use yt-dlp to write subtitle files without downloading the video."""
    try:
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", "zh-Hans,zh-CN,zh,en,zh-Hant",
            "--sub-format", "json3/srv3/vtt/srt/best",
            "--no-playlist",
            "-o", os.path.join(tmp_dir, "%(id)s.%(ext)s"),
        ]
        cmd += _get_cookie_args(platform)
        cmd.append(url)
        _run_ytdlp(cmd)
    except Exception as e:
        log(f"yt-dlp subtitle download failed: {e}", "WARN")
        return None, []

    sub_files = (
        glob.glob(os.path.join(tmp_dir, "*.vtt"))
        + glob.glob(os.path.join(tmp_dir, "*.srt"))
        + glob.glob(os.path.join(tmp_dir, "*.json3"))
        + glob.glob(os.path.join(tmp_dir, "*.srv3"))
    )
    if not sub_files:
        return None, []

    for sf in sub_files:
        text, cues = _parse_subtitle_file(sf)
        if text:
            return text, cues
    return None, []


def _parse_subtitle_file(filepath):
    """Parse VTT/SRT/JSON3/SRV3 subtitle file into (text, cues)."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None, []

    if not content.strip():
        return None, []

    if ext == ".json3":
        return _parse_json3_subtitle(content)
    elif ext in (".vtt", ".srt"):
        return _parse_vtt_srt(content)
    elif ext == ".srv3":
        return _parse_srv3_subtitle(content)
    return None, []


def _parse_json3_subtitle(content):
    try:
        data = json.loads(content)
        events = data.get("events", [])
        lines = []
        cues = []
        for event in events:
            segs = event.get("segs", [])
            text = "".join(s.get("utf8", "") or "" for s in segs).strip()
            if not text or text == "\n":
                continue
            lines.append(text)
            start_ms = event.get("tStartMs")
            dur_ms = event.get("dDurationMs") or 0
            if start_ms is not None:
                cue = _make_cue(start_ms / 1000.0, (start_ms + dur_ms) / 1000.0, text)
                if cue:
                    cues.append(cue)
        return ("\n".join(lines) if lines else None), cues
    except Exception:
        return None, []


def _parse_srv3_subtitle(content):
    lines = []
    cues = []
    for match in re.finditer(r"<p([^>]*)>(.*?)</p>", content, re.DOTALL):
        attrs, inner = match.group(1), match.group(2)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        if not text:
            continue
        lines.append(text)
        t_match = re.search(r'\bt="(\d+)"', attrs)
        d_match = re.search(r'\bd="(\d+)"', attrs)
        if t_match:
            start = int(t_match.group(1)) / 1000.0
            duration = int(d_match.group(1)) / 1000.0 if d_match else 0
            cue = _make_cue(start, start + duration, text)
            if cue:
                cues.append(cue)
    return ("\n".join(lines) if lines else None), cues


def _parse_vtt_srt(content):
    lines = []
    cues = []
    seen = set()
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").strip())
    for block in blocks:
        timing = None
        text_lines = []
        for raw in block.splitlines():
            line = raw.strip()
            if not line:
                continue
            if re.match(r"^\d+$", line):
                continue
            if re.match(r"^WEBVTT", line):
                continue
            if re.match(r"^NOTE\b", line):
                continue
            timed = re.search(r"([\d:,.]+)\s*-->\s*([\d:,.]+)", line)
            if timed:
                timing = timed
                continue
            text_lines.append(re.sub(r"<[^>]+>", "", line).strip())
        text = " ".join(t for t in text_lines if t)
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(text)
        if timing:
            start = _timestamp_to_seconds(timing.group(1))
            end = _timestamp_to_seconds(timing.group(2))
            cue = _make_cue(start, end, text)
            if cue:
                cues.append(cue)
    return ("\n".join(lines) if lines else None), cues


def _ytdlp_download_audio(url, tmp_dir, platform="generic"):
    """Download audio only via yt-dlp for Whisper transcription."""
    audio_path = os.path.join(tmp_dir, "audio.m4a")
    try:
        cmd = [
            "yt-dlp",
            "-f", "m4a/bestaudio[ext=m4a]/bestaudio",
            "--no-playlist",
            "-o", audio_path,
        ]
        cmd += _get_cookie_args(platform)
        cmd.append(url)
        rc, _ = _run_ytdlp(cmd, timeout=300)
        if rc == 0 and os.path.exists(audio_path):
            return audio_path
    except Exception as e:
        log(f"yt-dlp audio download failed: {e}", "WARN")

    found = glob.glob(os.path.join(tmp_dir, "audio.*"))
    return found[0] if found else None


def _ytdlp_download_video(url, tmp_dir, platform="generic"):
    """Download lowest-quality video via yt-dlp for frame extraction."""
    video_path = os.path.join(tmp_dir, "video.mp4")
    try:
        cmd = [
            "yt-dlp",
            "-f", "worstvideo[ext=mp4]+worstaudio/worst[ext=mp4]/worstvideo+worstaudio/worst",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "-o", video_path,
        ]
        cmd += _get_cookie_args(platform)
        cmd.append(url)
        rc, out = _run_ytdlp(cmd, timeout=300)
        if rc == 0 and os.path.exists(video_path):
            return video_path
        log(f"yt-dlp video download returned rc={rc}", "WARN")
    except Exception as e:
        log(f"yt-dlp video download failed: {e}", "WARN")

    found = glob.glob(os.path.join(tmp_dir, "video.*"))
    return found[0] if found else None


# ---------------------------------------------------------------------------
# Keyframe extraction
# ---------------------------------------------------------------------------

_ffmpeg_path_cache = None


def _get_ffmpeg():
    """Find ffmpeg executable. Caches after first lookup."""
    global _ffmpeg_path_cache
    if _ffmpeg_path_cache is not None:
        return _ffmpeg_path_cache or None

    path = shutil.which("ffmpeg")
    if path:
        _ffmpeg_path_cache = path
        return path

    if sys.platform == "win32":
        winget_links = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"
        )
        candidate = os.path.join(winget_links, "ffmpeg.exe")
        if os.path.isfile(candidate):
            _ffmpeg_path_cache = candidate
            return candidate

    _ffmpeg_path_cache = ""
    return None


def _check_ffmpeg():
    return _get_ffmpeg() is not None


def _get_ffprobe():
    """Find ffprobe next to ffmpeg."""
    ffmpeg = _get_ffmpeg()
    if not ffmpeg:
        return None
    ffprobe = os.path.join(os.path.dirname(ffmpeg), "ffprobe" + (".exe" if sys.platform == "win32" else ""))
    if os.path.isfile(ffprobe):
        return ffprobe
    return shutil.which("ffprobe")


def _get_video_duration_ffprobe(video_path):
    """Get video duration in seconds using ffprobe."""
    ffprobe = _get_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def _extract_frames_ffmpeg(video_path, output_dir, num_frames, duration=None):
    """Extract evenly-spaced frames from a video using ffmpeg.
    Returns list of frame dicts with 'path' and 'timestamp'."""
    ffmpeg = _get_ffmpeg()
    if not ffmpeg:
        log("ffmpeg not installed, skipping frame extraction", "WARN")
        return []

    if duration is None:
        duration = _get_video_duration_ffprobe(video_path)
    if not duration or duration <= 0:
        return []

    if duration < 10:
        num_frames = min(num_frames, 3)

    os.makedirs(output_dir, exist_ok=True)

    frames = []
    for i in range(num_frames):
        ts = duration * (i + 0.5) / num_frames
        out_path = os.path.join(output_dir, f"frame_{i + 1:03d}.jpg")
        try:
            subprocess.run(
                [ffmpeg, "-ss", f"{ts:.2f}", "-i", video_path,
                 "-frames:v", "1", "-q:v", "3",
                 "-vf", "scale='min(640,iw)':-1",
                 "-y", out_path],
                capture_output=True, timeout=15,
            )
            if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
                frames.append({"path": out_path, "timestamp": ts})
        except Exception:
            pass

    log(f"Extracted {len(frames)} keyframes from video")
    return frames


def extract_keyframes(url, platform, config, play_url=None, duration=None):
    """Download video and extract keyframes. Returns list of frame dicts or [].
    Frame dicts have 'path' (absolute) and 'timestamp' (seconds)."""
    if not config.get("extract_frames", True):
        return []
    if not _check_ffmpeg():
        log("ffmpeg not installed, skipping frame extraction", "WARN")
        return []

    num_frames = config.get("frames_per_video", 6)
    cache_key = _cache_key(url)
    frame_dir = os.path.join(SCREENSHOTS_DIR, cache_key)

    existing = sorted(glob.glob(os.path.join(frame_dir, "frame_*.jpg")))
    if existing:
        ttl_days = config.get("cache_ttl_days", 7)
        if ttl_days > 0:
            age_days = (time.time() - os.path.getmtime(existing[0])) / 86400
            if age_days > ttl_days:
                log(f"Cached frames expired ({age_days:.1f}d > {ttl_days}d)")
                shutil.rmtree(frame_dir, ignore_errors=True)
                existing = []
    if existing:
        log(f"Using {len(existing)} cached frames")
        frames = []
        for p in existing:
            idx = int(os.path.basename(p).split("_")[1].split(".")[0]) - 1
            ts = (duration or 0) * (idx + 0.5) / max(len(existing), 1)
            frames.append({"path": p, "timestamp": ts})
        return frames

    tmp_dir = tempfile.mkdtemp(prefix="frames_")
    try:
        video_path = None

        if play_url and platform == "douyin":
            video_path = _download_douyin_audio(play_url, tmp_dir)
        elif play_url and platform == "xiaohongshu":
            video_path = _download_xhs_video(play_url, tmp_dir)
        elif play_url and platform == "bilibili":
            video_path = _download_bili_media(play_url, tmp_dir)

        if not video_path and _check_ytdlp():
            log("Downloading video for frame extraction...")
            video_path = _ytdlp_download_video(url, tmp_dir, platform)

        if not video_path:
            return []

        if not duration:
            duration = _get_video_duration_ffprobe(video_path)

        return _extract_frames_ffmpeg(video_path, frame_dir, num_frames, duration)
    except Exception as e:
        log(f"Frame extraction failed: {e}", "WARN")
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def extract_with_ytdlp(url, platform="generic"):
    """Generic extraction using yt-dlp: metadata + subtitles."""
    if not _check_ytdlp():
        return None

    yt_info = _ytdlp_extract_info(url, platform)
    info = {
        "title": "",
        "author": "",
        "duration": 0,
        "description": "",
    }
    if yt_info:
        info["title"] = yt_info.get("title", "") or yt_info.get("fulltitle", "")
        info["author"] = yt_info.get("uploader", "") or yt_info.get("channel", "")
        info["duration"] = yt_info.get("duration", 0) or 0
        info["description"] = yt_info.get("description", "")

    tmp_dir = tempfile.mkdtemp(prefix="video_sub_")
    try:
        log(f"Trying yt-dlp subtitle extraction for {platform}...")
        text, cues = _ytdlp_extract_subs(url, tmp_dir, platform)
        if text:
            return _make_result(info, platform, url, text, "yt_dlp_subs", cues=cues)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return _make_result(info, platform, url)


# ---------------------------------------------------------------------------
# Whisper ASR fallback
# ---------------------------------------------------------------------------

def transcribe_with_whisper(url, platform, info, config, play_url=None):
    """Download audio then transcribe with Whisper.
    For Douyin, uses play_url for direct download if yt-dlp fails."""
    whisper_mode = config.get("whisper_mode", "disabled")
    if whisper_mode == "disabled":
        return None

    tmp_dir = tempfile.mkdtemp(prefix="whisper_")
    try:
        log("Downloading audio for Whisper transcription...")
        audio_path = None

        if play_url:
            log("Trying direct download via play_url...")
            if platform == "xiaohongshu":
                audio_path = _download_xhs_video(play_url, tmp_dir)
            elif platform == "bilibili":
                audio_path = _download_bili_media(play_url, tmp_dir)
            else:
                audio_path = _download_douyin_audio(play_url, tmp_dir)

        if not audio_path and _check_ytdlp():
            audio_path = _ytdlp_download_audio(url, tmp_dir, platform)

        if not audio_path:
            if not _check_ytdlp():
                log("yt-dlp not installed and no direct download available", "ERROR")
            else:
                log("Failed to download audio", "ERROR")
            return None

        if whisper_mode == "api":
            text, cues = _whisper_api(audio_path, config)
        elif whisper_mode == "local":
            text, cues = _whisper_local(audio_path, config)
        else:
            log(f"Unknown whisper_mode: {whisper_mode}", "ERROR")
            return None

        if text:
            source = f"whisper_{whisper_mode}"
            return _make_result(info, platform, url, text, source, cues=cues)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return None


def _whisper_api(audio_path, config):
    """Transcribe using OpenAI Whisper API. Returns (text, cues)."""
    api_key = config.get("openai_api_key", "")
    if not api_key:
        log("openai_api_key not configured in config.json", "ERROR")
        return None, []

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        language = config.get("language", "zh")

        file_size = os.path.getsize(audio_path)
        max_size = 25 * 1024 * 1024  # 25MB API limit

        if file_size > max_size:
            log(f"Audio file too large ({file_size // 1024 // 1024}MB), splitting...", "WARN")
            return _whisper_api_chunked(audio_path, client, language)

        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        return _whisper_response_to_payload(resp)
    except ImportError:
        log("openai package not installed. Run: pip install openai", "ERROR")
    except Exception as e:
        log(f"Whisper API failed: {e}", "ERROR")
    return None, []


def _whisper_response_to_payload(resp, time_offset=0.0):
    """Normalize an OpenAI transcription response into (text, cues)."""
    if resp is None:
        return None, []
    if isinstance(resp, str):
        text = resp.strip()
        return (text or None), []
    segments = getattr(resp, "segments", None)
    if segments is None and isinstance(resp, dict):
        segments = resp.get("segments")
    if segments:
        return _cues_from_segments(segments, time_offset=time_offset)
    text = getattr(resp, "text", None)
    if text is None and isinstance(resp, dict):
        text = resp.get("text")
    text = (text or "").strip()
    return (text or None), []


def _whisper_api_chunked(audio_path, client, language):
    """Split large audio and transcribe in chunks. Returns (text, cues)."""
    try:
        from pydub import AudioSegment
    except ImportError:
        log("pydub not installed, cannot split audio. Run: pip install pydub", "ERROR")
        return None, []

    try:
        audio = AudioSegment.from_file(audio_path)
        chunk_ms = 10 * 60 * 1000  # 10 minutes per chunk
        chunks = [audio[i:i + chunk_ms] for i in range(0, len(audio), chunk_ms)]

        parts = []
        cues = []
        for i, chunk in enumerate(chunks):
            log(f"Transcribing chunk {i + 1}/{len(chunks)}...")
            chunk_path = audio_path + f".chunk{i}.m4a"
            chunk.export(chunk_path, format="ipod")
            with open(chunk_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
            text, chunk_cues = _whisper_response_to_payload(resp, time_offset=i * 600)
            if text:
                parts.append(text.strip())
            cues.extend(chunk_cues)
            os.unlink(chunk_path)

        if not parts:
            return None, []
        return "\n".join(parts), cues
    except Exception as e:
        log(f"Chunked transcription failed: {e}", "ERROR")
        return None, []


def _whisper_local(audio_path, config):
    """Transcribe using faster-whisper (local model). Returns (text, cues)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log("faster-whisper not installed. Run: pip install faster-whisper", "ERROR")
        return None, []

    model_size = config.get("whisper_model", "base")
    language = config.get("language", "zh")

    last_error = None
    for device, compute_type in (("auto", "auto"), ("cpu", "int8")):
        try:
            log(f"Loading Whisper model '{model_size}' on {device}/{compute_type}...")
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
            segments, _ = model.transcribe(audio_path, language=language)
            return _cues_from_segments(segments)
        except Exception as e:
            last_error = e
            log(f"Whisper {device}/{compute_type} failed: {e}", "WARN")
    log(f"Local Whisper transcription failed: {last_error}", "ERROR")
    return None, []


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------

def format_duration(seconds):
    if not seconds or not isinstance(seconds, (int, float)):
        return "00:00"
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


MAX_POST_IMAGES = 20
XHS_PIC_TOKEN_RE = re.compile(
    r"https?://sns-webpic-qc\.xhscdn\.com/\d+/[0-9a-z]+/(\S+)!"
)


def _make_result(
    info,
    platform,
    url,
    subtitle_text=None,
    source=None,
    error=None,
    cues=None,
    content_type="video",
    images=None,
    images_truncated=False,
    images_total=None,
):
    result = {
        "info": info,
        "platform": platform,
        "url": url,
        "subtitle_text": subtitle_text,
        "source": source,
        "error": error,
        "content_type": content_type,
    }
    if cues:
        result["cues"] = cues
    if content_type == "post":
        result["images"] = images or []
        if images_truncated:
            result["images_truncated"] = True
            if images_total is not None:
                result["images_total"] = images_total
    return result


def _make_post_result(
    info,
    platform,
    url,
    subtitle_text="",
    images=None,
    error=None,
    images_truncated=False,
    images_total=None,
):
    return _make_result(
        info,
        platform,
        url,
        subtitle_text=subtitle_text,
        source="note_page",
        error=error,
        content_type="post",
        images=images,
        images_truncated=images_truncated,
        images_total=images_total,
    )


def _download_file(url, dest, headers):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if not data or len(data) < 32:
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        log(f"Image download failed: {e}", "WARN")
        return False


def _guess_image_ext(url):
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if "format/png" in url:
        return ".png"
    return ".jpg"


def _download_post_images(page_url, image_urls, referer, user_agent):
    """Download min(len, 20) images. Returns (images, truncated, total) or None on any miss."""
    total = len(image_urls)
    truncated = total > MAX_POST_IMAGES
    selected = image_urls[:MAX_POST_IMAGES]
    if not selected:
        return [], truncated, total

    dest_dir = os.path.join(IMAGES_DIR, _cache_key(page_url))
    headers = {
        "User-Agent": user_agent,
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    images = []
    for index, img_url in enumerate(selected, start=1):
        dest = os.path.join(dest_dir, f"{index:02d}{_guess_image_ext(img_url)}")
        if os.path.exists(dest) and os.path.getsize(dest) > 32:
            images.append({"path": os.path.abspath(dest), "index": index})
            continue
        if not _download_file(img_url, dest, headers):
            return None
        images.append({"path": os.path.abspath(dest), "index": index})
    return images, truncated, total


def _finalize_post(info, platform, url, image_urls, referer, user_agent):
    title = (info.get("title") or "").strip()
    desc = (info.get("description") or "").strip()
    subtitle_text = desc or title
    processable = min(len(image_urls or []), MAX_POST_IMAGES)
    if not title and processable == 0:
        return _make_post_result(
            info, platform, url,
            subtitle_text=subtitle_text,
            error="Post has no title and no images",
        )
    downloaded = _download_post_images(url, image_urls or [], referer, user_agent)
    if downloaded is None:
        return _make_post_result(
            info, platform, url,
            subtitle_text=subtitle_text,
            error="Failed to download all post images",
        )
    images, truncated, total = downloaded
    return _make_post_result(
        info, platform, url,
        subtitle_text=subtitle_text,
        images=images,
        images_truncated=truncated,
        images_total=total if truncated else None,
    )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def extract(url, config):
    """
    Main entry point. Tries cache, then platform-specific extraction,
    then yt-dlp subs, then Whisper ASR. Returns a result dict.
    """
    url = _normalize_input_url(url)

    # Phase 0: check cache
    cached = _read_cache(url)
    if cached:
        return cached

    platform = detect_platform(url)
    log(f"Detected platform: {platform}")

    # Phase 1: platform-specific subtitle extraction (fast, no heavy deps)
    result = None
    play_url = None

    if platform == "bilibili":
        result = extract_bilibili(url)
    elif platform == "youtube":
        result = extract_youtube(url)
    elif platform == "douyin":
        result = extract_douyin(url)
    elif platform == "xiaohongshu":
        result = extract_xiaohongshu(url)
    elif platform == "weixin":
        result = extract_weixin(url)

    if result:
        play_url = result.get("_play_url")

    if result and result.get("content_type") == "post":
        if not result.get("error"):
            _write_cache(url, result)
        return result

    final_result = None

    if result and result.get("subtitle_text"):
        final_result = result
    else:
        # Phase 2: yt-dlp subtitle extraction (works for all platforms)
        info = result["info"] if result else {"title": "", "author": "", "duration": 0, "description": ""}

        if _check_ytdlp():
            ytdlp_result = extract_with_ytdlp(url, platform)
            if ytdlp_result:
                if ytdlp_result.get("subtitle_text"):
                    if not info.get("title") and ytdlp_result["info"].get("title"):
                        info = ytdlp_result["info"]
                    final_result = _make_result(
                        info, platform, url,
                        ytdlp_result["subtitle_text"],
                        ytdlp_result["source"],
                        cues=ytdlp_result.get("cues"),
                    )
                if not info.get("title") and ytdlp_result["info"].get("title"):
                    info = ytdlp_result["info"]
        else:
            log("yt-dlp not installed. Install with: pip install yt-dlp", "WARN")

        # Phase 3: Whisper ASR fallback
        if not final_result:
            whisper_result = transcribe_with_whisper(url, platform, info, config, play_url=play_url)
            if whisper_result and whisper_result.get("subtitle_text"):
                final_result = whisper_result

        # All methods failed
        if not final_result:
            error_parts = ["No subtitles or transcript could be extracted."]
            if not _check_ytdlp():
                error_parts.append("Install yt-dlp for broader platform support: pip install yt-dlp")
            if platform == "youtube":
                try:
                    import youtube_transcript_api  # noqa: F401
                except ImportError:
                    error_parts.append("Install youtube-transcript-api for YouTube: pip install youtube-transcript-api")
            if platform in PLATFORMS_NEEDING_COOKIES and not _cookie_args_result:
                error_parts.append(
                    f"Douyin/Xiaohongshu/TikTok require browser cookies. "
                    f"Export cookies: install 'Get cookies.txt LOCALLY' browser extension, "
                    f"visit the site, export, and save the file (e.g. www.douyin.com_cookies.txt "
                    f"or cookies.txt) in: {SCRIPT_DIR}"
                )
            whisper_mode = config.get("whisper_mode", "disabled")
            if whisper_mode == "disabled":
                error_parts.append("Enable Whisper in config.json for audio transcription fallback.")
            return _make_result(info, platform, url, error="\n".join(error_parts))

    # Phase 4: Extract keyframes (runs for all successful extractions)
    duration = (final_result.get("info") or {}).get("duration", 0)
    frames = extract_keyframes(url, platform, config, play_url=play_url, duration=duration)
    if frames:
        final_result["frames"] = frames

    _write_cache(url, final_result)
    return final_result


def _clear_cache():
    """Remove cached results, screenshots, and downloaded images."""
    removed = 0
    for d in [CACHE_DIR, SCREENSHOTS_DIR, IMAGES_DIR]:
        if os.path.isdir(d):
            removed += sum(len(files) for _, _, files in os.walk(d))
            shutil.rmtree(d, ignore_errors=True)
    log(f"Cleared cache: {removed} files removed")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--clear-cache":
        _clear_cache()
        return

    if len(sys.argv) < 2:
        print("Usage: python extract_content.py <URL>", file=sys.stderr)
        print("       python extract_content.py --clear-cache", file=sys.stderr)
        print("  Supports: Bilibili, YouTube, Douyin, Xiaohongshu, TikTok, Weixin, and 1800+ sites", file=sys.stderr)
        sys.exit(1)

    url = _normalize_input_url(sys.argv[1])
    config = load_config()

    log(f"Extracting content for: {url}")
    result = extract(url, config)

    if not result:
        log("Extraction returned no result", "ERROR")
        sys.exit(1)

    info = result.get("info", {})
    content_type = result.get("content_type", "video")
    output = {
        "content_type": content_type,
        "title": info.get("title", ""),
        "author": info.get("author", ""),
        "description": info.get("description", ""),
        "platform": result.get("platform", "unknown"),
        "url": result.get("url", url),
    }
    if content_type != "post":
        output["duration"] = format_duration(info.get("duration", 0))

    if result.get("error"):
        output["error"] = result["error"]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        sys.exit(1)

    output["source"] = result.get("source", "unknown")
    output["subtitle_text"] = result.get("subtitle_text") or ""

    if content_type == "post":
        output["images"] = result.get("images") or []
        if result.get("images_truncated"):
            output["images_truncated"] = True
            if result.get("images_total") is not None:
                output["images_total"] = result["images_total"]
    else:
        if result.get("cues"):
            output["cues"] = result["cues"]
        if result.get("frames"):
            output["frames"] = [
                {"path": f["path"], "timestamp": format_duration(int(f["timestamp"]))}
                for f in result["frames"]
            ]

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
