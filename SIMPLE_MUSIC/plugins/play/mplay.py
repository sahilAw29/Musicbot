"""Movie/series video player using movie-downloader-api.vercel.app."""
import asyncio
import html
import secrets
import time
from typing import Any

import aiohttp
from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from SIMPLE_MUSIC import app
from SIMPLE_MUSIC.utils.stream.stream import stream
from SIMPLE_MUSIC.utils.stream.queue import put_queue_index
from SIMPLE_MUSIC.utils.database import get_lang
from strings import get_string
from config import BANNED_USERS

API_BASE = "https://movie-downloader-api.vercel.app/api"
_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 900


def _purge() -> None:
    now = time.time()
    for token, item in list(_CACHE.items()):
        if now - item["created"] > _CACHE_TTL:
            _CACHE.pop(token, None)


def _save(results: list[dict]) -> str:
    _purge()
    token = secrets.token_urlsafe(5).replace("-", "_")
    _CACHE[token] = {"created": time.time(), "results": results}
    return token


def _get(token: str) -> dict | None:
    _purge()
    return _CACHE.get(token)


def _quality_options(episode: dict) -> list[dict]:
    return [q for q in episode.get("qualities", []) if q.get("download_url") or q.get("downloadUrl")]

def _quality_for_episode(episode: dict, wanted: str) -> dict | None:
    options = _quality_options(episode)
    if not options:
        return None
    wanted = str(wanted or "").lower()
    return next((q for q in options if str(q.get("quality", "")).lower() == wanted), options[0])


def _episode_label(ep: dict) -> str:
    season = ep.get("season", 1)
    number = ep.get("episode", "?")
    return f"S{season} • E{number}"

def _languages(episodes: list[dict]) -> list[str]:
    """Preserve the API's language order, without silently dropping languages."""
    out = []
    for ep in episodes:
        language = str(ep.get("language") or "Unknown")
        if language not in out:
            out.append(language)
    return out


async def _fetch_search(query: str) -> list[dict]:
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{API_BASE}/search", params={"q": query}) as response:
            if response.status != 200:
                return []
            data = await response.json(content_type=None)
            return data.get("results", []) if isinstance(data, dict) else []


@app.on_message(
    filters.command(["mplay", "movieplay", "seriesplay"], prefixes=["/", "!", ".", ""])
    & filters.group & ~BANNED_USERS
)
async def mplay_command(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🎬 <b>Movie/Series Player</b>\n\n"
            "Use: <code>/mplay movie or series name</code>\n"
            "Example: <code>/mplay overflow</code>"
        )
    query = message.text.split(None, 1)[1].strip()
    if len(query) < 2:
        return await message.reply_text("❌ Search ke liye kam se kam 2 letters likho.")
    wait = await message.reply_text("🔎 <b>Movie/series search ho rahi hai...</b>")
    try:
        results = await _fetch_search(query)
    except Exception as exc:
        return await wait.edit_text(f"❌ Movie API unavailable: <code>{html.escape(str(exc)[:120])}</code>")
    if not results:
        return await wait.edit_text("❌ Is naam ki movie/series nahi mili.")
    token = _save(results[:10])
    _CACHE[token]["mode"] = "mxplay" if message.command[0].lower() == "mxplay" else "mplay"
    buttons = []
    for index, item in enumerate(results[:10]):
        title = str(item.get("title") or "Untitled")[:32]
        year = item.get("year") or ""
        kind = item.get("type") or ""
        buttons.append([InlineKeyboardButton(f"{index + 1}. {title} {year} · {kind}", callback_data=f"mps|{token}|{index}")])
    await wait.edit_text(
        f"🎬 <b>Search results for:</b> <i>{html.escape(query[:80])}</i>\n\n"
        + ("Movie/series select karo — mxplay mein saare episodes nonstop chalenge:"
           if _CACHE[token]["mode"] == "mxplay" else "Movie/series select karo:"),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^mps\|"))
async def mplay_select(_, cq: CallbackQuery):
    _, token, raw_index = cq.data.split("|")
    item = _get(token)
    if not item:
        return await cq.answer("Search expire ho gayi, /mplay dobara run karo.", show_alert=True)
    index = int(raw_index)
    results = item["results"]
    if index >= len(results):
        return await cq.answer("Result unavailable.", show_alert=True)
    result = results[index]
    item["selected_result"] = index
    episodes = result.get("episodes") or []
    languages = _languages(episodes)
    if not languages:
        return await cq.answer("Is title ke episodes available nahi hain.", show_alert=True)
    buttons = [
        InlineKeyboardButton(lang.title(), callback_data=f"mpl|{token}|{index}|{n}")
        for n, lang in enumerate(languages)
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    subtitle_info = result.get("subtitles") or "API metadata mein subtitles listed nahi hain"
    await cq.message.edit_text(
        f"🎬 <b>{html.escape(str(result.get('title') or 'Selected title'))}</b>\n"
        f"📅 {result.get('year', '—')} · {result.get('type', '—')} · ⭐ {result.get('rating', '—')}\n"
        f"📝 <b>API subtitles:</b> {html.escape(str(subtitle_info))}\n\n"
        f"🌐 <b>Audio language choose karo ({len(languages)} available):</b>",
        reply_markup=InlineKeyboardMarkup(rows),
    )


@app.on_callback_query(filters.regex(r"^mpl\|"))
async def mplay_language(_, cq: CallbackQuery):
    _, token, raw_index, raw_lang = cq.data.split("|")
    item = _get(token)
    if not item:
        return await cq.answer("Search expire ho gayi.", show_alert=True)
    index, lang_index = int(raw_index), int(raw_lang)
    result = item["results"][index]
    episodes = result.get("episodes") or []
    languages = _languages(episodes)
    if lang_index >= len(languages):
        return await cq.answer("Language unavailable.", show_alert=True)
    language = languages[lang_index]
    seasons = sorted({int(ep.get("season", 1)) for ep in episodes if str(ep.get("language") or "Unknown") == language})
    item["selected_language"] = language
    item["selected_result"] = index
    if not seasons:
        return await cq.answer("Is language ke episodes available nahi hain.", show_alert=True)
    if len(seasons) == 1:
        return await _show_episodes(cq, item, result, language, seasons[0])
    buttons = [[InlineKeyboardButton(f"Season {season}", callback_data=f"mpsn|{token}|{index}|{lang_index}|{season}") for season in seasons]]
    await cq.message.edit_text(
        f"🎬 <b>{html.escape(str(result.get('title') or 'Title'))}</b> · <b>{html.escape(language.title())}</b>\n\n"
        f"📚 <b>Season choose karo ({len(seasons)} available):</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def _show_episodes(cq, item, result, language: str, season: int):
    selected = [
        ep for ep in result.get("episodes", [])
        if str(ep.get("language") or "Unknown") == language and int(ep.get("season", 1)) == season
    ]
    unique, seen = [], set()
    for ep in selected:
        key = (ep.get("season", 1), ep.get("episode"))
        if key not in seen:
            seen.add(key)
            unique.append(ep)
    item["selected_season"] = season
    item["episodes"] = unique
    buttons = [InlineKeyboardButton(f"E{ep.get('episode', '?')}", callback_data=f"mpe|{next(k for k,v in _CACHE.items() if v is item)}|{n}") for n, ep in enumerate(unique)]
    rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
    await cq.message.edit_text(
        f"🎬 <b>{html.escape(str(result.get('title') or 'Title'))}</b> · "
        f"<b>S{season} · {html.escape(language.title())}</b>\n\n"
        f"📺 <b>Episode choose karo ({len(unique)} available):</b>",
        reply_markup=InlineKeyboardMarkup(rows),
    )

@app.on_callback_query(filters.regex(r"^mpsn\|"))
async def mplay_season(_, cq: CallbackQuery):
    _, token, raw_index, raw_lang, raw_season = cq.data.split("|")
    item = _get(token)
    if not item:
        return await cq.answer("Search expire ho gayi.", show_alert=True)
    index, lang_index, season = int(raw_index), int(raw_lang), int(raw_season)
    result = item["results"][index]
    languages = _languages(result.get("episodes") or [])
    if lang_index >= len(languages):
        return await cq.answer("Language unavailable.", show_alert=True)
    await _show_episodes(cq, item, result, languages[lang_index], season)

@app.on_callback_query(filters.regex(r"^mpe\|"))
async def mplay_episode(_, cq: CallbackQuery):
    _, token, raw_episode = cq.data.split("|")
    item = _get(token)
    if not item:
        return await cq.answer("Search expire ho gayi.", show_alert=True)
    episode_index = int(raw_episode)
    episodes = item.get("episodes") or []
    if episode_index >= len(episodes):
        return await cq.answer("Episode unavailable.", show_alert=True)
    episode = episodes[episode_index]
    qualities = _quality_options(episode)
    if not qualities:
        return await cq.answer("Is episode ki quality available nahi hai.", show_alert=True)
    item["selected_episode"] = episode_index
    buttons = [[InlineKeyboardButton(
        f"{q.get('quality') or 'Auto'} · {q.get('format') or 'video'}",
        callback_data=f"mpq|{token}|{episode_index}|{n}",
    ) for n, q in enumerate(qualities)]]
    await cq.message.edit_text(
        f"🎬 <b>{html.escape(str(item['results'][item.get('selected_result', 0)].get('title') or 'Title'))}</b>\n"
        f"📺 <b>{_episode_label(episode)}</b> · {html.escape(str(item.get('selected_language', 'Unknown')).title())}\n\n"
        "⚙️ <b>Video quality choose karo:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^mpq\|"))
async def mplay_quality(_, cq: CallbackQuery):
    _, token, raw_episode, raw_quality = cq.data.split("|")
    item = _get(token)
    if not item:
        return await cq.answer("Search expire ho gayi.", show_alert=True)
    episode_index, quality_index = int(raw_episode), int(raw_quality)
    episodes = item.get("episodes") or []
    if episode_index >= len(episodes):
        return await cq.answer("Episode unavailable.", show_alert=True)
    qualities = _quality_options(episodes[episode_index])
    if quality_index >= len(qualities):
        return await cq.answer("Quality unavailable.", show_alert=True)
    quality = qualities[quality_index]
    url = quality.get("download_url") or quality.get("downloadUrl")
    title = str(item["results"][item.get("selected_result", 0)].get("title") or "Movie")
    ep = episodes[episode_index]
    result_item = item["results"][item.get("selected_result", 0)]
    api_image = result_item.get("poster") or result_item.get("thumbnail")
    api_stream_title = f"{title} • {_episode_label(ep)} • {item.get('selected_language', 'Unknown')}"
    await cq.answer("▶️ Video starting...")
    await cq.message.edit_text(
        f"▶️ <b>Starting video</b>\n\n🎬 {html.escape(title)}\n"
        f"📺 {_episode_label(ep)} · {html.escape(str(item.get('selected_language', 'Unknown')).title())}\n"
        f"⚙️ {html.escape(str(quality.get('quality') or 'Auto'))}"
    )
    try:
        language = await get_lang(cq.message.chat.id)
        _ = get_string(language)
        if item.get("mode") == "mxplay":
            # Start the selected episode, then append every remaining episode
            # to the same queue. The normal call transition automatically
            # advances through these index streams without any manual action.
            episodes_to_queue = []
            wanted_quality = quality.get("quality")
            for ep in episodes[episode_index:]:
                selected_quality = _quality_for_episode(ep, wanted_quality)
                if selected_quality:
                    ep_url = selected_quality.get("download_url") or selected_quality.get("downloadUrl")
                    episodes_to_queue.append((ep, ep_url, selected_quality))
            if not episodes_to_queue:
                return await cq.message.edit_text("❌ Is language ke episodes mein playable quality nahi mili.")
            first_ep, first_url, first_quality = episodes_to_queue[0]
            await stream(
                _, cq.message, cq.from_user.id, first_url, cq.message.chat.id,
                cq.from_user.mention, cq.message.chat.id, video=True,
                streamtype="index", forceplay=False,
                stream_title=api_stream_title,
                stream_duration=f"{quality.get('quality') or 'Auto'} {quality.get('format') or 'video'}",
                stream_image=api_image,
            )
            # stream() puts the first item in db; append the rest for seamless playback.
            for ep, ep_url, selected_quality in episodes_to_queue[1:]:
                await put_queue_index(
                    cq.message.chat.id, cq.message.chat.id, "index_url",
                    f"{title} {_episode_label(ep)}",
                    "ᴜʀʟ sᴛʀᴇᴀᴍ", cq.from_user.mention, ep_url, "video",
                    image=api_image,
                )
            await cq.message.edit_text(
                f"▶️ <b>MXPLAY started</b>\n\n🎬 {html.escape(title)}\n"
                f"📺 {html.escape(str(item.get('selected_language', 'Unknown')).title())}\n"
                f"▶️ {_episode_label(first_ep)} → {_episode_label(episodes_to_queue[-1][0])}\n"
                f"📦 <b>{len(episodes_to_queue)} episodes queued</b>\n\n"
                "⏭️ Episodes automatically nonstop play honge."
            )
        else:
            await stream(
                _, cq.message, cq.from_user.id, url, cq.message.chat.id,
                cq.from_user.mention, cq.message.chat.id, video=True,
                streamtype="index", forceplay=False,
                stream_title=api_stream_title,
                stream_duration=f"{quality.get('quality') or 'Auto'} {quality.get('format') or 'video'}",
                stream_image=api_image,
            )
    except Exception as exc:
        await cq.message.edit_text(f"❌ Video start nahi ho saka: <code>{html.escape(str(exc)[:180])}</code>")
