# -----------------------------------------------
# /admins → media (random /start video) ke saath admin panel
# Har section ka button dabao, us section ke commands + use karne ka tarika khulega.
# Group staff ki list ab /staff ya /adminlist se.
# -----------------------------------------------
import os
from urllib.parse import urlsplit

import config
from pyrogram import filters
from pyrogram.types import CallbackQuery, Message

from SIMPLE_MUSIC import LOGGER, app
from SIMPLE_MUSIC.plugins.bot.start import START_MEDIA_FILE_IDS
from SIMPLE_MUSIC.utils.fancy_buttons import (
    BLUE, GREEN, RED,
    ICON_BACK, ICON_BOT, ICON_CLIP, ICON_CLOSE, ICON_CROWN, ICON_EYES, ICON_MOD, ICON_MUSIC,
    ICON_OK, ICON_SPARKLE,
    btn, markup_variants, pe,
)
from SIMPLE_MUSIC.utils.start_videos_db import random_start_media

HOME = f"""{pe(ICON_CROWN, "👑")} <b>⏤͟͞Aᴅᴍɪɴ ꭙ Pᴀɴᴇʟ</b>

ɴɪᴄʜᴇ ᴋɪsɪ ʙʜɪ ʙᴜᴛᴛᴏɴ ᴘᴀʀ ᴛᴀᴘ ᴋᴀʀᴏ, ᴜs sᴇᴄᴛɪᴏɴ ᴋᴇ sᴀᴀʀᴇ ᴄᴏᴍᴍᴀɴᴅs ᴀᴜʀ ᴜsᴇ ᴋᴀʀɴᴇ ᴋᴀ ᴛᴀʀɪᴋᴀ ᴋʜᴜʟ ᴊᴀʏᴇɢᴀ.

{pe(ICON_SPARKLE, "✨")} = ɴᴀʏᴇ sʏsᴛᴇᴍ (sᴛᴀʀᴛ ᴠɪᴅᴇᴏ, ᴀɪ ᴏɴ/ᴏғғ, sᴛʏʟɪsʜ ғᴏɴᴛ)"""

SECTIONS = {
    "new_video": ("Sᴛᴀʀᴛ Vɪᴅᴇᴏ", f"""{pe(ICON_SPARKLE, "✨")} <b>/start ʀᴀɴᴅᴏᴍ ᴠɪᴅᴇᴏ</b> {pe(ICON_CROWN, "👑")} [ᴏᴡɴᴇʀ/sᴜᴅᴏ]
ʜᴀʀ /start ᴘᴀʀ ʀᴀɴᴅᴏᴍ ᴠɪᴅᴇᴏ (sᴘᴏɪʟᴇʀ ᴍᴇ) ᴀᴀᴛᴀ ʜᴀɪ.

<blockquote><b>/addvideo</b> → ᴋɪsɪ ʙʜɪ ᴠɪᴅᴇᴏ / ɢɪғ / ᴠɪᴅᴇᴏ ғɪʟᴇ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ ʙʜᴇᴊᴏ. ʏᴀ ᴠɪᴅᴇᴏ ᴋᴇ ᴄᴀᴘᴛɪᴏɴ ᴍᴇ /addvideo ʟɪᴋʜᴏ.
<b>/startvideos</b> → sᴀᴀʀᴇ sᴀᴠᴇᴅ ᴠɪᴅᴇᴏs ᴋɪ ɴᴜᴍʙᴇʀ ʟɪsᴛ
<b>/showvideo 2</b> → 2 ɴᴜᴍʙᴇʀ ᴡᴀʟᴀ ᴠɪᴅᴇᴏ ᴅᴇᴋʜᴏ
<b>/delvideo 2</b> → 2 ɴᴜᴍʙᴇʀ ᴅᴇʟᴇᴛᴇ (ʏᴀ sᴀᴠᴇᴅ ᴠɪᴅᴇᴏ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ /delvideo)
<b>/delvideo all</b> → sᴀʙ ᴅᴇʟᴇᴛᴇ</blockquote>"""),
    "new_ai": ("Aɪ + Fᴏɴᴛ", f"""{pe(ICON_BOT, "🤖")} <b>ᴀɪ ᴏɴ / ᴏғғ</b> [ɢʀᴏᴜᴘ ᴀᴅᴍɪɴ]
<blockquote>{pe(ICON_OK, "✅")} <b>/ai on</b> → ʙᴏᴛ ᴋᴇ ᴍsɢ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴏ ᴛᴏ ᴀɪ ᴊᴀᴡᴀʙ ᴅᴇɢᴀ
<b>/ai off</b> → ᴀɪ ʙɪʟᴋᴜʟ ᴄʜᴜᴘ (ʀᴇᴘʟʏ + /ask ᴅᴏɴᴏ ʙᴀɴᴅ)
<b>/ai</b> → ᴀʙʜɪ ᴏɴ ʜᴀɪ ʏᴀ ᴏғғ
ʜᴀʀ ɢʀᴏᴜᴘ ᴋᴀ ᴀʟᴀɢ sᴇᴛᴛɪɴɢ</blockquote>

{pe(ICON_SPARKLE, "✨")} <b>sᴛʏʟɪsʜ ғᴏɴᴛ</b> [sᴀʙᴋᴇ ʟɪʏᴇ]
<blockquote><b>/font Nazariya Music</b> → ⏤͟͞Nᴀᴢᴀʀɪʏᴀ ꭙ Mᴜꜱɪᴄ
ʏᴀ ᴋɪsɪ ᴛᴇxᴛ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ /font
ɴɪᴄʜᴇ ᴋᴇ ʙᴜᴛᴛᴏɴs sᴇ 40+ ᴅᴜsʀᴇ ғᴏɴᴛ</blockquote>"""),
    "music": ("Mᴜꜱɪᴄ", f"""{pe(ICON_MUSIC, "🎵")} <b>ᴍᴜsɪᴄ ᴄᴏɴᴛʀᴏʟ</b>
<blockquote><b>/pause</b> • <b>/resume</b> → ɢᴀᴀɴᴀ ʀᴏᴋᴏ / ᴄʜᴀʟᴀᴏ
<b>/skip</b> → ᴀɢʟᴀ ɢᴀᴀɴᴀ
<b>/end</b> ʏᴀ <b>/stop</b> → sᴀʙ ʙᴀɴᴅ, ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀ
<b>/seek 30</b> • <b>/seekback 30</b> → 30 sᴇᴄ ᴀᴀɢᴇ / ᴘᴇᴇᴄʜᴇ
<b>/loop 3</b> → 3 ʙᴀᴀʀ ʀᴇᴘᴇᴀᴛ • <b>/loop disable</b>
<b>/shuffle</b> • <b>/queue</b> • <b>/player</b>
<b>/speed</b> → ᴘʟᴀʏʙᴀᴄᴋ sᴘᴇᴇᴅ</blockquote>
ᴄʜᴀɴɴᴇʟ ᴘʟᴀʏ ᴋᴇ ʟɪʏᴇ ᴀᴀɢᴇ <b>c</b> : /cpause /cskip /cend

<b>🔐 ᴀᴜᴛʜ</b>
<blockquote><b>/auth</b> [ʀᴇᴘʟʏ/ᴜsᴇʀ] → ʙɪɴᴀ ᴀᴅᴍɪɴ ᴍᴜsɪᴄ ᴄᴏɴᴛʀᴏʟ ᴅᴏ
<b>/unauth</b> • <b>/authusers</b></blockquote>"""),
    "mod": ("Mᴏᴅᴇʀᴀᴛɪᴏɴ", f"""{pe(ICON_MOD, "🔨")} <b>ᴍᴏᴅᴇʀᴀᴛɪᴏɴ</b> (ʀᴇᴘʟʏ ʏᴀ @ᴜsᴇʀ)
<blockquote><b>/ban</b> • <b>/unban</b> • <b>/unbanall</b>
<b>/mute</b> • <b>/unmute</b> • <b>/unmuteall</b>
<b>/tmute @user 2m</b> → 2 ᴍɪɴ ᴍᴜᴛᴇ (m/h/d)
<b>/promote</b> • <b>/fullpromote</b> • <b>/demote</b>
<b>/purge</b> → ʀᴇᴘʟʏ ᴡᴀʟᴇ ᴍsɢ sᴇ ɴɪᴄʜᴇ ᴛᴀᴋ ᴅᴇʟᴇᴛᴇ
<b>/spurge</b> → ᴄʜᴜᴘᴄʜᴀᴘ ᴘᴜʀɢᴇ • <b>/del</b> → ᴇᴋ ᴍsɢ ᴅᴇʟᴇᴛᴇ
<b>/zombies</b> → ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs ʜᴀᴛᴀᴏ</blockquote>"""),
    "group": ("Gʀᴏᴜᴘ", f"""{pe(ICON_CLIP, "📎")} <b>ɢʀᴏᴜᴘ sᴇᴛᴛɪɴɢs</b>
<blockquote><b>/pin</b> • <b>/unpin</b> • <b>/unpinall</b> • <b>/pinned</b>
<b>/settitle</b> • <b>/setdiscription</b>
<b>/setphoto</b> (ᴘʜᴏᴛᴏ ᴘᴀʀ ʀᴇᴘʟʏ) • <b>/removephoto</b>
<b>/welcome on/off</b> • <b>/nightmode</b>
<b>/imposter on/off</b> → ɴᴀᴀᴍ ʙᴀᴅʟɴᴇ ᴡᴀʟᴏ ᴘᴀʀ ɴᴀᴢᴀʀ
<b>/vclogger on/off</b> • <b>/givelink</b></blockquote>

<b>📝 ɴᴏᴛᴇs & ғɪʟᴛᴇʀs</b>
<blockquote><b>/save name</b> (ʀᴇᴘʟʏ) • <b>/get name</b> ʏᴀ <b>#name</b>
<b>/notes</b> • <b>/clear name</b> • <b>/clearall</b>
<b>/filter word</b> (ʀᴇᴘʟʏ) • <b>/filters</b>
<b>/stopfilter word</b> • <b>/stopall</b></blockquote>"""),
    "tag": ("Tᴀɢ + Iɴꜰᴏ", f"""📢 <b>ᴛᴀɢ / ᴍᴇɴᴛɪᴏɴ</b>
<blockquote><b>/tagall</b> • <b>/mention text</b> • <b>/admintag</b>
<b>/gmtag</b> • <b>/gntag</b> • <b>/hitag</b> • <b>/shayari</b> • <b>/utag text</b>
sᴛᴏᴘ : <b>/cancelall</b> • /gmstop • /gnstop • /histop • /shstop</blockquote>

{pe(ICON_EYES, "👀")} <b>ɪɴғᴏ</b>
<blockquote><b>/staff</b> ʏᴀ <b>/adminlist</b> → ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs
<b>/bots</b> → ɢʀᴏᴜᴘ ᴋᴇ ʙᴏᴛs
<b>/admins</b> → ʏᴇʜɪ ᴘᴀɴᴇʟ</blockquote>"""),
}

# section → (button colour, premium icon). Icon na ho to button me normal emoji rehta hai.
BUTTON_LOOK = {
    "new_video": (GREEN, ICON_SPARKLE, ""),
    "new_ai": (GREEN, ICON_BOT, ""),
    "music": (BLUE, ICON_MUSIC, ""),
    "mod": (RED, ICON_MOD, ""),
    "group": (BLUE, ICON_CLIP, ""),
    "tag": (BLUE, ICON_EYES, ""),
}
ORDER = [["new_video", "new_ai"], ["music", "mod"], ["group", "tag"]]


def _section_btn(key):
    style, icon, emoji = BUTTON_LOOK[key]
    # icon off ho to normal emoji dikhe
    if icon and not getattr(config, "BUTTON_ICON", False):
        emoji = {"new_video": "✨ ", "new_ai": "🤖 ", "music": "🎵 ", "mod": "🔨 ", "group": "📎 ", "tag": "👀 "}.get(key, "")
    return btn(emoji + SECTIONS[key][0], callback_data=f"admp_{key}", style=style, icon=icon)


def _close_btn():
    return btn("ᴄʟᴏsᴇ" if getattr(config, "BUTTON_ICON", False) else "✖ ᴄʟᴏsᴇ",
               callback_data="admp_x", style=RED, icon=ICON_CLOSE)


def _home_rows():
    rows = [[_section_btn(k) for k in row] for row in ORDER]
    rows.append([_close_btn()])
    return rows


def _back_rows():
    back = "ʙᴀᴄᴋ" if getattr(config, "BUTTON_ICON", False) else "⬅ ʙᴀᴄᴋ"
    return [[btn(back, callback_data="admp_home", style=BLUE, icon=ICON_BACK), _close_btn()]]


def _media_senders(client, media):
    """(function, field, value) list — panel ke saath kaunsa media bhejna hai."""
    if isinstance(media, dict):
        kind, value = media.get("type"), media.get("media")
        if kind == "video":
            return [(client.send_video, "video", value)]
        if kind == "animation":
            return [(client.send_animation, "animation", value)]
        media = value
    if not media:
        return []
    cached = START_MEDIA_FILE_IDS.get(media)
    if cached:
        return [(client.send_video, "video", cached)]
    ext = os.path.splitext(urlsplit(str(media)).path)[1].lower()
    if ext in (".mp4", ".mov", ".m4v", ".mkv", ".webm"):
        return [(client.send_video, "video", media)]
    if ext == ".gif":
        return [(client.send_animation, "animation", media)]
    return [(client.send_photo, "photo", media), (client.send_video, "video", media)]


@app.on_message(filters.command(["admins", "admincmds", "adminhelp"]), group=-2)
async def admin_panel(client, message: Message):
    senders = _media_senders(client, await random_start_media())
    last_error = None
    for markup in markup_variants(_home_rows()):  # colour+icon → colour → simple
        for send, field, value in senders:
            try:
                return await send(message.chat.id, **{field: value}, caption=HOME, reply_markup=markup)
            except Exception as error:
                last_error = error
        try:
            return await message.reply_text(HOME, reply_markup=markup, disable_web_page_preview=True)
        except Exception as error:
            last_error = error
    LOGGER(__name__).warning(f"/admins failed: {last_error}")
    await message.reply_text(f"❖ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ ɴᴀʜɪ ᴋʜᴜʟᴀ : <code>{last_error}</code>")


@app.on_callback_query(filters.regex(r"^admp_"), group=-2)
async def admin_panel_cb(_, query: CallbackQuery):
    try:
        await _handle_admin_cb(query)
    finally:
        # start.py ka "home" handler admp_home ko na pakde
        query.stop_propagation()


async def _handle_admin_cb(query: CallbackQuery):
    key = query.data[5:]
    if key == "x":
        try:
            await query.message.delete()
        except Exception:
            pass
        return await query.answer()
    if key == "home":
        text, rows = HOME, _home_rows()
    elif key in SECTIONS:
        text, rows = SECTIONS[key][1], _back_rows()
    else:
        return await query.answer()
    for markup in markup_variants(rows):
        try:
            if query.message.media:
                await query.message.edit_caption(text, reply_markup=markup)
            else:
                await query.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
            break
        except Exception as error:
            if "MESSAGE_NOT_MODIFIED" in str(error):
                break
    await query.answer()
