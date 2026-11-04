# -----------------------------------------------
# 🔸 YORU MUSIC BOT Project
# 🔹 Developed & Maintained by: Yoru Music Bot ()
# 📅 Copyright © 2026 – All Rights Reserved
#
# 📖 License:
# This source code is open for educational and non-commercial use ONLY.
# You are required to retain this credit in all copies or substantial portions of this file.
# Commercial use, redistribution, or removal of this notice is strictly prohibited
# without prior written permission from the author.
#
# ❤️ Made with dedication and love by Yoru Music Bot
# -----------------------------------------------

import asyncio
import hashlib
import json
import os
import re
import time
from typing import Union
from urllib.parse import quote_plus

import aiohttp
import aiofiles
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from py_yt import Playlist, VideosSearch

from SIMPLE_MUSIC import LOGGER
from SIMPLE_MUSIC.utils.cookies import fetch_cookie_file
from SIMPLE_MUSIC.utils.formatters import time_to_seconds

VIDEO_ID_RE = re.compile(r"(?:v=|vi=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


def _extract_video_id(link: str):
    """Pull the 11-char video ID out of any YouTube URL shape (watch?v=, youtu.be/, shorts/, ?si= etc.)."""
    match = VIDEO_ID_RE.search(link)
    return match.group(1) if match else None



import config
from config import (API_URL, VIDEO_API_URL, API_KEY, YT_API_KEY, YTPROXY_URL,
                    VDA_API_URL, VDA_API_KEY, VDA_AUDIO_QUALITY, VDA_VIDEO_FORMAT,
                    YT_SEARCH_API_URL, VDA_KEYS_URL, GAMEOVER_API_URL,
                    GAMEOVER_API_KEY)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
CLIENT_SESSION = None

VDA_KEYS_CACHE = None
SEARCH_CACHE = {}
DETAILS_CACHE = {}
VIDEO_INFO_CACHE = {}
RELATED_CACHE = {}
RELATED_CACHE_TTL_SECONDS = 600
GAMEOVER_CACHE = {}
ANNIE_QUERIES = {}   # vidid -> exact text the user asked for
ANNIE_TRACKS = {}    # vidid -> details dict, so inline buttons reopen the same track
ANNIE_FILES = {}     # (vidid, is_video) -> stream URL or downloaded file
ANNIE_STREAMABLE = {}  # API URL -> True if ffmpeg can play it directly
ANNIE_META_CACHE = {}  # query -> resolved title/duration/thumbnail/link
ANNIE_META_TASKS = {}  # placeholder vidid -> search still running in the background
ANNIE_LOCKS = {}     # file path -> lock, so one song is never downloaded twice at once
CACHE_TTL_SECONDS = 120


async def _get_vda_keys():
    """Load remote JSON keys once, with an environment key as fallback."""
    global VDA_KEYS_CACHE
    if VDA_KEYS_CACHE is not None:
        return VDA_KEYS_CACHE
    keys = []
    if VDA_API_KEY:
        keys.append(VDA_API_KEY)
    try:
        session = await get_session()
        async with session.get(VDA_KEYS_URL, timeout=aiohttp.ClientTimeout(total=8, sock_connect=4, sock_read=6)) as response:
            if response.status == 200:
                payload = await response.json(content_type=None)
                if isinstance(payload, dict):
                    keys.extend(str(value).strip() for value in payload.values() if str(value).strip())
                elif isinstance(payload, list):
                    keys.extend(str(value).strip() for value in payload if str(value).strip())
    except Exception:
        pass
    VDA_KEYS_CACHE = list(dict.fromkeys(keys))
    return VDA_KEYS_CACHE


async def resolve_gameover(query: str):
    """Resolve an audio search to a direct stream URL through GameOver."""
    if not query or not GAMEOVER_API_URL or not GAMEOVER_API_KEY:
        return None
    try:
        session = await get_session()
        async with session.get(
            GAMEOVER_API_URL,
            params={"key": GAMEOVER_API_KEY, "search": query},
            headers={"Accept": "application/json", "User-Agent": "YoruMusicBot/1.0"},
            timeout=aiohttp.ClientTimeout(total=12, sock_connect=4, sock_read=8),
        ) as response:
            if response.status != 200:
                return None
            data = await response.json(content_type=None)
        if isinstance(data, dict) and data.get("status") == "success" and data.get("stream_url"):
            return data
    except Exception:
        pass
    return None


async def engine_vda(link: str, is_video: bool, path: str) -> str:
    """Try each VDA key in order, polling the first accepted job to completion."""
    keys = await _get_vda_keys()
    if not keys:
        return None
    session = await get_session()
    for api_key in keys:
        try:
            params = {
                "url": link,
                "format": VDA_VIDEO_FORMAT if is_video else "mp3",
                "apikey": api_key,
                "allow_extended_duration": "0",
                "no_merge": "0",
            }
            if not is_video:
                params["audio_quality"] = VDA_AUDIO_QUALITY
            async with session.get(
                f"{VDA_API_URL}/ajax/download.php",
                params=params,
                timeout=aiohttp.ClientTimeout(total=18, sock_connect=5, sock_read=12),
            ) as response:
                if response.status != 200:
                    continue
                job = await response.json(content_type=None)
            if not job.get("success"):
                continue
            download_url = job.get("url")
            progress_url = job.get("progress_url")
            job_id = job.get("id")
            if not download_url and job_id:
                progress_url = progress_url or f"{VDA_API_URL}/api/progress?id={job_id}"
                for _ in range(60):
                    await asyncio.sleep(1)
                    async with session.get(
                        progress_url,
                        timeout=aiohttp.ClientTimeout(total=10, sock_connect=4, sock_read=7),
                    ) as progress_response:
                        if progress_response.status != 200:
                            continue
                        status = await progress_response.json(content_type=None)
                    download_url = status.get("download_url") or status.get("url")
                    if download_url or str(status.get("progress")).lower() in ("error", "failed"):
                        break
            if download_url:
                result = await _download_stream(download_url, path)
                if result:
                    return result
        except Exception:
            continue
    return None


async def search_youtube_api(query: str):
    """Resolve music through GameOver and retain its direct stream URL."""
    cache_key = " ".join(str(query).split()).lower()
    now = time.monotonic()
    cached = SEARCH_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    try:
        resolved = await resolve_gameover(query)
        if resolved and resolved.get("stream_url"):
            # Synthetic ID keeps the existing queue compatible while ensuring
            # download() retrieves this exact resolver stream from cache.
            resolver_id = str(resolved.get("track_id") or resolved.get("video_id") or cache_key)
            source_video_id = str(resolved.get("video_id") or "").strip()
            vid = f"gameover:{resolver_id}"
            title = str(resolved.get("title") or query)
            artist = str(resolved.get("artist") or "")
            duration_text = str(resolved.get("duration") or "00:00")
            # The API exposes the original YouTube video_id instead of an
            # image field. Build the exact matching thumbnail from that ID.
            thumbnail = (
                f"https://i.ytimg.com/vi/{source_video_id}/hqdefault.jpg"
                if len(source_video_id) == 11 else None
            )
            result = {
                "videoId": vid,
                "title": f"{title} — {artist}" if artist else title,
                "durationText": duration_text,
                "durationSeconds": int(resolved.get("duration_sec") or time_to_seconds(duration_text)),
                "thumbnail": thumbnail,
                "watchUrl": f"https://www.youtube.com/watch?v={source_video_id}" if len(source_video_id) == 11 else None,
                "uploader": artist,
                "directStreamUrl": resolved["stream_url"],
            }
            GAMEOVER_CACHE[vid] = (now, resolved["stream_url"])
            results = [result]
            SEARCH_CACHE[cache_key] = (now, results)
            return results
    except Exception:
        pass
    # Compatibility fallback for queries unavailable in the resolver.
    try:
        session = await get_session()
        async with session.get(YT_SEARCH_API_URL, params={"p": query}, timeout=aiohttp.ClientTimeout(total=10, sock_connect=4, sock_read=7)) as response:
            if response.status != 200:
                return []
            payload = await response.json(content_type=None)
        results = payload.get("results", []) if isinstance(payload, dict) else []
        SEARCH_CACHE[cache_key] = (now, results)
        return results
    except Exception:
        return []


async def get_session():
    global CLIENT_SESSION
    if CLIENT_SESSION is None or CLIENT_SESSION.closed:
        CLIENT_SESSION = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0))
    return CLIENT_SESSION


async def engine_media_api(link: str, is_video: bool, path: str) -> str:
    """Download audio/video through the supplied media API stream URL."""
    try:
        session = await get_session()
        params = {"type": "video" if is_video else "audio", "url": link}
        if is_video:
            params["quality"] = config.MEDIA_API_VIDEO_QUALITY
        async with session.get(
            f"{config.MEDIA_API_BASE_URL}/download",
            params=params,
            timeout=aiohttp.ClientTimeout(total=25, sock_connect=5, sock_read=20),
        ) as response:
            if response.status != 200:
                return None
            payload = await response.json(content_type=None)
        stream_url = payload.get("stream_url") if isinstance(payload, dict) else None
        if stream_url:
            return await _download_stream(stream_url, path)
    except Exception:
        pass
    return None

def _result_thumbnail(result, video_id):
    """Return the thumbnail belonging to the same API result/video ID."""
    raw = result.get("thumbnail")
    if isinstance(raw, dict):
        for key in ("maxres", "high", "medium", "default"):
            value = raw.get(key)
            if isinstance(value, dict) and value.get("url"):
                return value["url"].split("?")[0]
            if isinstance(value, str) and value:
                return value.split("?")[0]
    elif isinstance(raw, list):
        for value in raw:
            if isinstance(value, dict) and value.get("url"):
                return value["url"].split("?")[0]
            if isinstance(value, str) and value:
                return value.split("?")[0]
    elif isinstance(raw, str) and raw:
        return raw.split("?")[0]
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


async def _download_stream(url, path, headers=None):
    try:
        session = await get_session()
        # Total download time unlimited; a short stalled-read timeout enables quick retry.
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=12)
        
        async with session.get(url, headers=headers, timeout=timeout) as response:
            if response.status == 200:
                async with aiofiles.open(path, mode='wb') as f:
                    # 4MB chunks improve throughput while keeping memory bounded.
                    async for chunk in response.content.iter_chunked(4 * 1024 * 1024):
                        await f.write(chunk)
                if os.path.exists(path) and os.path.getsize(path) > 1024:
                    return path
    except:
        pass
    if os.path.exists(path):
        try: os.remove(path)
        except: pass
    return None

async def engine_shrutibots(vid_id: str, is_video: bool, path: str) -> str:
    try:
        session = await get_session()
        v_type = "video" if is_video else "audio"
        async with session.get(f"{API_URL}/download", params={"url": vid_id, "type": v_type}, timeout=5) as resp:
            if resp.status != 200: return None
            token = (await resp.json()).get("download_token")
            if not token: return None
        return await _download_stream(f"{API_URL}/stream/{vid_id}?type={v_type}&token={token}", path)
    except: return None

async def engine_xbit(vid_id: str, is_video: bool, path: str) -> str:
    if not YTPROXY_URL or not YT_API_KEY: return None
    try:
        session = await get_session()
        headers = {"x-api-key": YT_API_KEY}
        async with session.get(f"{YTPROXY_URL}/info/{vid_id}", headers=headers, timeout=5) as resp:
            if resp.status != 200: return None
            data = await resp.json()
        if data.get('status') == 'success':
            url = data['video_url'] if is_video else data['audio_url']
            return await _download_stream(url, path, headers)
    except: return None

async def engine_nexgen(vid_id: str, is_video: bool, path: str) -> str:
    if not API_KEY: return None
    try:
        url = f"{VIDEO_API_URL}/video/{vid_id}?api={API_KEY}" if is_video else f"{API_URL}/song/{vid_id}?api={API_KEY}"
        session = await get_session()
        async with session.get(url, timeout=5) as resp:
            if resp.status != 200: return None
            data = await resp.json()
            if data.get("status", "").lower() == "done" and data.get("link"):
                return await _download_stream(data.get("link"), path)
    except: return None


async def engine_shuvo(link: str, is_video: bool, path: str) -> str:
    SHUVO_API = "https://youtube-api-all-in-one-by-shuvo.onrender.com"
    SHUVO_KEY = "SHUVO-apis"
    try:
        import json as _json
        session = await get_session()
        headers = {"X-API-Key": SHUVO_KEY, "Content-Type": "application/json"}
        endpoint = "/api/download" if is_video else "/api/audio"
        payload = _json.dumps({"url": link}).encode()
        async with session.post(
            f"{SHUVO_API}{endpoint}", data=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=25)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        dl_url = (
            data.get("download_url") or data.get("audio_url") or
            data.get("url") or data.get("link") or
            (data.get("data") or {}).get("download_url") or
            (data.get("data") or {}).get("url")
        )
        if dl_url:
            return await _download_stream(dl_url, path)
    except Exception:
        pass
    return None

def annie_url(query: str, is_video: bool) -> str:
    # "_" is escaped because the queue detects vid_/live_/index_ inside this value.
    encoded = quote_plus(" ".join(str(query).split()), safe="").replace("_", "%5F")
    return f"{config.ANNIE_API_URL}/song/{'video' if is_video else 'audio'}?q={encoded}"


def _minutes_text(seconds) -> str:
    minutes, secs = divmod(int(seconds or 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def _has_duration(text) -> bool:
    try:
        return int(time_to_seconds(str(text))) > 0
    except Exception:
        return False


def _meta(title, vidid, duration, thumb=None):
    if not (vidid and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(vidid))):
        return None
    return {
        "title": str(title or "").strip(),
        "vidid": vidid,
        "duration_min": duration if _has_duration(duration) else "00:00",
        "thumb": (thumb or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg").split("?")[0],
        "link": f"https://www.youtube.com/watch?v={vidid}",
    }


async def _meta_from_youtube(query: str):
    """Direct YouTube search: real video ID, title, length and thumbnail."""
    payload = await VideosSearch(query, limit=1).next()
    items = (payload or {}).get("result") or []
    if not items:
        return None
    item = items[0]
    thumbs = item.get("thumbnails") or [{}]
    return _meta(item.get("title"), item.get("id"), item.get("duration"), thumbs[0].get("url"))


async def _meta_from_search_api(query: str):
    """Existing search services. GameOver IDs are mapped back to the YouTube ID."""
    results = await search_youtube_api(query)
    if not results:
        return None
    item = results[0]
    vidid = item.get("videoId")
    if str(vidid).startswith("gameover:"):
        vidid = _extract_video_id(str(item.get("watchUrl") or ""))
    return _meta(item.get("title"), vidid, item.get("durationText"), _result_thumbnail(item, vidid))


async def _probe_api_file(query: str):
    """Read the real length (and title tag) from the API's own audio file."""
    await asyncio.sleep(1.5)  # search usually answers first, saving this API call
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags=title",
        "-of", "json", annie_url(query, False),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 9)
    finally:
        if process.returncode is None:
            process.kill()
    info = json.loads(output or b"{}").get("format") or {}
    seconds = int(float(info.get("duration") or 0))
    return {"title": (info.get("tags") or {}).get("title"), "duration_min": _minutes_text(seconds)}


async def resolve_track_meta(query: str):
    """Ask every source at once and combine the answers: search supplies the
    video ID and thumbnail, the API file supplies the length if search cannot.
    One slow or dead service can no longer leave the card empty."""
    key = query.lower()
    if key in ANNIE_META_CACHE:
        return ANNIE_META_CACHE[key]
    found = probed = None
    tasks = [
        asyncio.create_task(_meta_from_youtube(query)),
        asyncio.create_task(_meta_from_search_api(query)),
        asyncio.create_task(_probe_api_file(query)),
    ]
    try:
        for future in asyncio.as_completed(tasks, timeout=11):
            try:
                result = await future
            except asyncio.TimeoutError:
                break
            except Exception as error:
                LOGGER(__name__).warning(f"Track details source failed for '{query}': {error!r}")
                continue
            if not result:
                continue
            if "vidid" not in result:
                probed = result
            elif not found or (_has_duration(result["duration_min"]) and not _has_duration(found["duration_min"])):
                found = result
            if found and (_has_duration(found["duration_min"]) or (probed and _has_duration(probed["duration_min"]))):
                break
    finally:
        for task in tasks:
            task.cancel()

    if not found and not probed:
        LOGGER(__name__).warning(f"No track details from any source for '{query}'")
        return None
    best = dict(found or {"title": "", "vidid": None, "duration_min": "00:00", "thumb": None, "link": ""})
    if probed:
        if not _has_duration(best["duration_min"]) and _has_duration(probed["duration_min"]):
            best["duration_min"] = probed["duration_min"]
        best["title"] = best["title"] or probed["title"]
    best["title"] = best["title"] or query
    ANNIE_META_CACHE[key] = best
    return best


async def annie_can_stream(url: str):
    """Decide how to play an API URL. True: stream it now. False: ffmpeg cannot
    open it live, so save it first. None: the API returned an error."""
    try:
        session = await get_session()
        async with session.get(
            url,
            headers={"User-Agent": "YoruMusicBot/1.0", "Range": "bytes=0-65535"},
            timeout=aiohttp.ClientTimeout(total=15, sock_connect=5, sock_read=12),
        ) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if response.status not in (200, 206) or content_type.startswith(("application/json", "text/")):
                LOGGER(__name__).warning(f"Annie API rejected {url}: {response.status} {content_type}")
                return None
            if response.status == 206:
                return True
            # No Range support: an MP4 only plays live if its index comes first.
            head = b""
            async for chunk in response.content.iter_chunked(16 * 1024):
                head += chunk
                if len(head) >= 64 * 1024:
                    break
            return b"moov" in head
    except Exception as error:
        LOGGER(__name__).warning(f"Annie API check failed for {url}: {error}")
        return False


async def annie_source(query: str, is_video: bool, vid_id: str = None):
    """Return the fastest playable source: the API URL, or a saved file when
    the API response cannot be streamed."""
    query = " ".join(str(query or "").split())
    if not query:
        return None
    url = annie_url(query, is_video)
    streamable = ANNIE_STREAMABLE.get(url)
    if streamable is None:
        streamable = await annie_can_stream(url)
        if streamable is None:
            return None
        ANNIE_STREAMABLE[url] = streamable
    if not streamable:
        return await annie_download(query, is_video, vid_id)
    if vid_id:
        ANNIE_FILES[(vid_id, is_video)] = url
    return url


def _annie_cached(vid_id: str, is_video: bool):
    source = ANNIE_FILES.get((vid_id, is_video))
    if source and (source.startswith("http") or os.path.exists(source)):
        return source
    return None


async def annie_download(query: str, is_video: bool, vid_id: str = None):
    """Save a song or video from the Annie API for playback from disk."""
    query = " ".join(str(query or "").split())
    if not query:
        return None
    kind = "video" if is_video else "audio"
    digest = hashlib.sha1(f"{kind}:{query.lower()}".encode("utf-8")).hexdigest()[:16]
    final_path = os.path.join(DOWNLOAD_DIR, f"annie_{digest}.{'mp4' if is_video else 'm4a'}")
    temp_path = f"{final_path}.part"

    async with ANNIE_LOCKS.setdefault(final_path, asyncio.Lock()):
        if not (os.path.exists(final_path) and os.path.getsize(final_path) > 1024):
            try:
                session = await get_session()
                async with session.get(
                    f"{config.ANNIE_API_URL}/song/{kind}",
                    params={"q": query},
                    headers={"User-Agent": "YoruMusicBot/1.0"},
                    timeout=aiohttp.ClientTimeout(total=900, sock_connect=15, sock_read=120),
                ) as response:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if response.status != 200 or content_type.startswith(("application/json", "text/")):
                        LOGGER(__name__).warning(
                            f"Annie API {kind} failed for '{query}': {response.status} {content_type}"
                        )
                        return None
                    async with aiofiles.open(temp_path, "wb") as output:
                        async for chunk in response.content.iter_chunked(256 * 1024):
                            await output.write(chunk)
                if os.path.getsize(temp_path) <= 1024:
                    return None
                os.replace(temp_path, final_path)
            except Exception as error:
                LOGGER(__name__).warning(f"Annie API {kind} error for '{query}': {error}")
                return None
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
    if vid_id:
        ANNIE_FILES[(vid_id, is_video)] = final_path
    return final_path


async def _core_download(link: str, is_video: bool) -> str:
    vid_id = link.split('v=')[-1].split('&')[0] if 'v=' in link else link.split("/")[-1].split("?")[0]
    ext = "mp4" if is_video else "mp3"
    final_path = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")

    if os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
        return final_path

    media_path = await engine_media_api(link, is_video, f"{final_path}_media_api")
    if media_path and os.path.exists(media_path):
        try:
            os.rename(media_path, final_path)
            return final_path
        except OSError:
            return media_path

    vda_path = await engine_vda(link, is_video, f"{final_path}_vda")
    if vda_path and os.path.exists(vda_path):
        try:
            os.rename(vda_path, final_path)
            return final_path
        except OSError:
            return vda_path

    # Keep the existing API engines as fallbacks. The final yt-dlp fallback
    # below also uses the configured cookie source when available.
    tasks = [
        asyncio.create_task(engine_shuvo(link, is_video, f"{final_path}_shuvo")),
        asyncio.create_task(engine_shrutibots(vid_id, is_video, f"{final_path}_shruti")),
        asyncio.create_task(engine_xbit(vid_id, is_video, f"{final_path}_xbit")),
        asyncio.create_task(engine_nexgen(vid_id, is_video, f"{final_path}_nexgen")),
    ]
    winner = None
    for future in asyncio.as_completed(tasks):
        try:
            res = await future
            if res:
                winner = res
                for task in tasks:
                    task.cancel()
                break
        except Exception:
            pass
    if winner and os.path.exists(winner):
        try:
            os.rename(winner, final_path)
            return final_path
        except OSError:
            return winner

    loop = asyncio.get_running_loop()
    def fallback_ytdl():
        cookie_path = asyncio.run(fetch_cookie_file())
        opts = {
            "format": "best[height<=480]/best" if is_video else "bestaudio/best",
            "outtmpl": final_path,
            "quiet": True,
            "nocheckcertificate": True,
            "no_warnings": True,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        if cookie_path:
            opts["cookiefile"] = cookie_path
        yt_dlp.YoutubeDL(opts).download([link])

    try:
        await loop.run_in_executor(None, fallback_ytdl)
    except Exception:
        return None
    return final_path if os.path.exists(final_path) and os.path.getsize(final_path) > 1024 else None

async def download_song(link: str) -> str:
    return await _core_download(link, is_video=False)

async def download_video(link: str) -> str:
    return await _core_download(link, is_video=True)


async def get_exact_video_info(video_id: str):
    """Resolve one exact YouTube ID without using a cookie file."""
    video_id = str(video_id or "").strip()
    cached = VIDEO_INFO_CACHE.get(video_id)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        return None
    link = f"https://www.youtube.com/watch?v={video_id}"
    loop = asyncio.get_running_loop()

    def extract_exact():
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "nocheckcertificate": True,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(link, download=False)

    data = None
    try:
        data = await loop.run_in_executor(None, extract_exact)
    except Exception:
        data = None

    if data and data.get("id") == video_id:
        duration_seconds = int(data.get("duration") or 0)
        mins, secs = divmod(duration_seconds, 60)
        result = {
            "videoId": video_id,
            "title": data.get("title") or "Unknown",
            "durationText": f"{mins:02d}:{secs:02d}",
            "durationSeconds": duration_seconds,
            "thumbnail": data.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "viewCount": data.get("view_count") or "Unknown",
            "channelTitle": data.get("uploader") or data.get("channel") or "YouTube",
            "channelUrl": data.get("channel_url") or "https://www.youtube.com",
            "publishedAt": data.get("upload_date") or "Unknown",
            "watchUrl": link,
        }
        VIDEO_INFO_CACHE[video_id] = (time.monotonic(), result)
        return result

    # yt-dlp failure: use the search API only if it returns the same exact ID.
    for result in await search_youtube_api(video_id):
        if str(result.get("videoId", "")) == video_id:
            VIDEO_INFO_CACHE[video_id] = (time.monotonic(), result)
            return result
    return None


async def get_related_videos(video_id: str, limit: int = 10):
    """
    Real 'up next' songs for a video — pulled from YouTube's own auto-generated
    Mix/Radio playlist (the same list YouTube itself uses for autoplay), not a
    generic title search (which mostly just returns re-uploads/covers of the
    same track). Returns a list of {"videoId", "title"} dicts, freshest first.
    """
    video_id = str(video_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        return []

    cached = RELATED_CACHE.get(video_id)
    now = time.monotonic()
    if cached and now - cached[0] < RELATED_CACHE_TTL_SECONDS:
        return cached[1]

    mix_url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
    loop = asyncio.get_running_loop()

    def extract_mix():
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "noplaylist": False,
            "playlistend": limit + 1,
            "nocheckcertificate": True,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(mix_url, download=False)

    try:
        data = await loop.run_in_executor(None, extract_mix)
    except Exception:
        data = None

    entries = []
    if data and data.get("entries"):
        for entry in data["entries"]:
            if not entry:
                continue
            vid = entry.get("id")
            if not vid or vid == video_id:
                continue  # skip the seed song itself
            entries.append({"videoId": vid, "title": entry.get("title") or "Unknown"})

    RELATED_CACHE[video_id] = (now, entries)
    return entries



class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message: messages.append(message_1.reply_to_message)
        for msg in messages:
            for ent in (msg.entities or []):
                if ent.type == MessageEntityType.URL: return (msg.text or msg.caption)[ent.offset : ent.offset + ent.length]
            for ent in (msg.caption_entities or []):
                if ent.type == MessageEntityType.TEXT_LINK: return ent.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid and link in ANNIE_TRACKS:
            track = ANNIE_TRACKS[link]
            return track["title"], track["duration_min"], int(time_to_seconds(track["duration_min"])), track["thumb"], link
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        # Direct YouTube URL — resolve the exact ID with cookies first.
        if re.search(self.regex, link):
            try:
                direct_id = _extract_video_id(link)
                exact = await get_exact_video_info(direct_id) if direct_id else None
                if exact:
                    vid = exact.get("videoId") or direct_id
                    dur_sec = int(exact.get("durationSeconds") or 0)
                    dur_min = exact.get("durationText") or "00:00"
                    thumbnail = exact.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                    return exact.get("title", "Unknown"), dur_min, dur_sec, thumbnail, vid
            except Exception:
                pass  # fallback to search below
        search_results = await search_youtube_api(link)
        if not search_results:
            raise ValueError("No YouTube results found")
        result = search_results[0]
        title = result.get("title", "Unknown")
        duration_min = result.get("durationText") or "00:00"
        vidid = result.get("videoId")
        thumbnail = _result_thumbnail(result, vidid) if vidid else ""
        if not vidid:
            raise ValueError("Search result has no video ID")
        duration_sec = int(result.get("durationSeconds") or time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        return (await self.details(link, videoid))[0]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        return (await self.details(link, videoid))[1]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        return (await self.details(link, videoid))[3]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            played = _annie_cached(link, True)
            if played:
                return 1, played
            link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            res = await download_video(link)
            return (1, res) if res else (0, "Video download failed")
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        try:
            session = await get_session()
            async with session.get(
                f"{config.MEDIA_API_BASE_URL}/playlist",
                params={"url": link},
                timeout=aiohttp.ClientTimeout(total=20, sock_connect=5, sock_read=15),
            ) as response:
                if response.status == 200:
                    payload = await response.json(content_type=None)
                    items = payload.get("items", []) if isinstance(payload, dict) else []
                    ids = [item.get("id") for item in items if item.get("id")]
                    if ids:
                        return ids[:limit]
        except Exception:
            pass
        try:
            videos = (await Playlist.get(link)).get("videos") or []
            return [data["id"] for data in videos[:limit] if data and data.get("id")]
        except: return []

    def _remember_track(self, query, details, placeholder=None):
        vidid = details["vidid"]
        ANNIE_QUERIES[vidid] = query
        ANNIE_TRACKS[vidid] = details
        if placeholder:
            ANNIE_QUERIES[placeholder] = query
            ANNIE_TRACKS[placeholder] = details
            for is_video in (False, True):
                source = ANNIE_FILES.get((placeholder, is_video))
                if source:
                    ANNIE_FILES[(vidid, is_video)] = source

    async def api_track(self, query: str):
        """Prepare a /play or /vplay text search. Playback uses the user's
        exact words and never waits long here: if search is not done within
        a moment it keeps running, and finish_metadata() fills in the card."""
        query = " ".join(str(query).split())
        placeholder = "annie_" + hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:12]
        task = asyncio.create_task(resolve_track_meta(query))
        await asyncio.wait({task}, timeout=0.8)
        found = task.result() if task.done() and not task.exception() else None
        if found:
            details = dict(found)
            details["vidid"] = details["vidid"] or placeholder
            details["thumb"] = details["thumb"] or config.STREAM_IMG_URL
            self._remember_track(query, details)
            return details, details["vidid"]
        details = {
            "title": query,
            "link": "",
            "vidid": placeholder,
            "duration_min": "00:00",
            "thumb": config.STREAM_IMG_URL,
        }
        if not task.done():
            ANNIE_META_TASKS[placeholder] = task
        self._remember_track(query, details)
        return details, placeholder

    def metadata_pending(self, vidid: str) -> bool:
        return vidid in ANNIE_META_TASKS

    async def finish_metadata(self, vidid: str, timeout: float = 5):
        """Wait briefly for a background search so the card can be complete.
        The search keeps running if it needs longer. Returns finished details,
        or None when nothing newer is available yet."""
        task = ANNIE_META_TASKS.get(vidid)
        if not task:
            return None
        await asyncio.wait({task}, timeout=timeout)
        if not task.done():
            return None
        ANNIE_META_TASKS.pop(vidid, None)
        found = None if task.cancelled() or task.exception() else task.result()
        if not found:
            return None
        details = dict(found)
        details["vidid"] = details["vidid"] or vidid
        details["thumb"] = details["thumb"] or config.STREAM_IMG_URL
        self._remember_track(ANNIE_QUERIES.get(vidid) or details["title"], details, placeholder=vidid)
        return details

    @staticmethod
    def card_link(username: str, vidid: str, title: str) -> str:
        """Title link for playback cards: the bot's track info page for real
        YouTube IDs, otherwise a YouTube search for the song."""
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", str(vidid)) and not str(vidid).startswith("annie_"):
            return f"https://t.me/{username}?start=info_{vidid}"
        return f"https://www.youtube.com/results?search_query={quote_plus(str(title))}"

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid and link in ANNIE_TRACKS:
            return ANNIE_TRACKS[link], link
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        # Direct YouTube URL — resolve the exact ID with cookies first.
        if re.search(self.regex, link):
            try:
                direct_id = _extract_video_id(link)
                exact = await get_exact_video_info(direct_id) if direct_id else None
                if exact:
                    vid = exact.get("videoId") or direct_id
                    return {
                        "title": exact.get("title", "Unknown"),
                        "link": exact.get("watchUrl") or f"https://www.youtube.com/watch?v={vid}",
                        "vidid": vid,
                        "duration_min": exact.get("durationText") or "00:00",
                        "thumb": exact.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    }, vid
            except Exception:
                pass  # fallback to search below
        search_results = await search_youtube_api(link)
        if not search_results:
            raise ValueError("No YouTube results found")
        result = search_results[0]
        vidid = result.get("videoId")
        if not vidid:
            raise ValueError("Search result has no video ID")
        thumb = _result_thumbnail(result, vidid)
        duration_text = result.get("durationText") or "00:00"
        cached_info = {
            "videoId": vidid,
            "title": result.get("title", "Unknown"),
            "durationText": duration_text,
            "durationSeconds": int(result.get("durationSeconds") or time_to_seconds(duration_text)),
            "thumbnail": thumb.split("?")[0],
            "watchUrl": result.get("watchUrl") or f"https://www.youtube.com/watch?v={vidid}",
        }
        VIDEO_INFO_CACHE[vidid] = (time.monotonic(), cached_info)
        return {
            "title": cached_info["title"],
            "link": cached_info["watchUrl"],
            "vidid": vidid,
            "duration_min": duration_text,
            "thumb": cached_info["thumbnail"],
        }, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        cookie_path = await fetch_cookie_file()
        base_fmt_opts = {
            "quiet": True,
            "no_warnings": True,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        if cookie_path:
            base_fmt_opts["cookiefile"] = cookie_path
        try:
            with yt_dlp.YoutubeDL(base_fmt_opts) as ydl:
                info = ydl.extract_info(link, download=False)
        except Exception:
            with yt_dlp.YoutubeDL(base_fmt_opts) as ydl:
                info = ydl.extract_info(link, download=False)
        return [{"format": f["format"], "filesize": f.get("filesize"), "format_id": f["format_id"], "ext": f["ext"], "format_note": f.get("format_note"), "yturl": link} for f in info["formats"] if "dash" not in str(f.get("format", "")).lower()], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        results = await search_youtube_api(link)
        if not results or query_type >= len(results):
            raise ValueError("No YouTube results found")
        res = results[query_type]
        thumb = _result_thumbnail(res, res["videoId"])
        return res.get("title", "Unknown"), res.get("durationText") or "00:00", thumb, res["videoId"]

    async def download(
        self, link: str, mystic, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None, title: Union[bool, str] = None,
    ) -> str:
        if videoid: link = self.base + link
        
        is_video = bool(video)
        vid_id = link.split('v=')[-1].split('&')[0] if 'v=' in link else link.split("/")[-1].split("?")[0]

        cached = _annie_cached(vid_id, is_video)
        if cached:
            return cached, True

        query = ANNIE_QUERIES.get(vid_id) or title
        if not query:
            try:
                query = (await self.details(link))[0]
            except Exception:
                query = link
        source = await annie_source(query, is_video, vid_id)
        return (source, True) if source else (None, False)
