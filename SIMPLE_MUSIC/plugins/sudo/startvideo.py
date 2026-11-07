# -----------------------------------------------
# /start random video — owner/sudo commands
#
#  /addvideo        → kisi bhi video/GIF/video-file par reply karke bhejo
#                     (ya video ke caption me /addvideo, ya /addvideo <link>)
#  /delvideo 2      → list ka 2 number wala video delete
#  /delvideo        → kisi saved video par reply karke bhi delete hota hai
#  /delvideo all    → saare video delete (fir START_IMG_URL wapas chalega)
#  /startvideos     → saare saved video ki list
#  /showvideo 2     → 2 number wala video dekh lo
# -----------------------------------------------
import os

from pyrogram import filters
from pyrogram.types import Message

from SIMPLE_MUSIC import app
from SIMPLE_MUSIC.misc import SUDOERS
from SIMPLE_MUSIC.utils.start_videos_db import (
    add_start_video,
    clear_start_videos,
    delete_start_video,
    get_start_videos,
)


def _media_of(msg: Message):
    """Saved-ready media: (unique_key, file_id, type) ya None."""
    if not msg:
        return None
    if msg.video:
        return msg.video.file_unique_id, msg.video.file_id, "video"
    if msg.animation:
        return msg.animation.file_unique_id, msg.animation.file_id, "animation"
    return None


def _needs_convert(msg: Message):
    """Video file (document) ya round video — inko pehle normal video banana padega."""
    if not msg:
        return None
    doc = msg.document
    if doc and (
        (doc.mime_type or "").startswith("video/")
        or (doc.file_name or "").lower().endswith((".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"))
    ):
        return doc.file_unique_id
    if msg.video_note:
        return msg.video_note.file_unique_id
    return None


async def _convert_to_video(client, message: Message, source: Message):
    """File ko download karke normal video ki tarah dobara upload karo."""
    status = await message.reply_text("⏳ ᴠɪᴅᴇᴏ ʀᴇᴀᴅʏ ᴋᴀʀ ʀᴀʜᴀ ʜᴏᴏɴ...")
    path = None
    try:
        path = await source.download()
        sent = await client.send_video(message.chat.id, path, caption="✅ /start ᴠɪᴅᴇᴏ", supports_streaming=True)
        return sent.video.file_unique_id, sent.video.file_id, "video"
    finally:
        try:
            await status.delete()
        except Exception:
            pass
        if path:
            try:
                os.remove(path)
            except Exception:
                pass


# Kaam karne ke 3 tareeke:
#  1) kisi video/GIF/video-file par reply karke /addvideo
#  2) video bhejte waqt caption me /addvideo likh do
#  3) /addvideo <direct link>
@app.on_message(filters.command(["addvideo", "addstartvideo"]) & SUDOERS, group=-2)
async def add_video_cmd(client, message: Message):
    source = message.reply_to_message
    found = _media_of(source) or _media_of(message)
    if not found:
        if not _needs_convert(source) and _needs_convert(message):
            source = message
        if _needs_convert(source):
            try:
                found = await _convert_to_video(client, message, source)
            except Exception as e:
                return await message.reply_text(f"❖ ᴠɪᴅᴇᴏ ᴀᴅᴅ ɴᴀʜɪ ʜᴜᴀ : <code>{e}</code>")

    text = message.text or message.caption or ""
    if not found and len(text.split()) > 1:
        link = text.split(None, 1)[1].strip()
        if link.startswith("http"):
            found = link, link, "url"

    if not found:
        return await message.reply_text(
            "❖ <b>ᴠɪᴅᴇᴏ ᴋᴀɪsᴇ ᴀᴅᴅ ᴋᴀʀᴇɪɴ :</b>\n"
            "• ᴋɪsɪ ʙʜɪ ᴠɪᴅᴇᴏ / ɢɪғ / ᴠɪᴅᴇᴏ ғɪʟᴇ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ <code>/addvideo</code>\n"
            "• ʏᴀ ᴠɪᴅᴇᴏ ᴋᴇ ᴄᴀᴘᴛɪᴏɴ ᴍᴇ <code>/addvideo</code> ʟɪᴋʜᴋᴇ ʙʜᴇᴊᴏ"
        )

    key, media, kind = found
    added = await add_start_video(key, media, kind, message.from_user.id)
    total = len(await get_start_videos())
    if not added:
        return await message.reply_text(f"❖ ʏᴇ ᴠɪᴅᴇᴏ ᴘᴇʜʟᴇ sᴇ ᴀᴅᴅ ʜᴀɪ.\n๏ ᴛᴏᴛᴀʟ ᴠɪᴅᴇᴏs : <code>{total}</code>")
    await message.reply_text(
        f"✅ ᴠɪᴅᴇᴏ ᴀᴅᴅ ʜᴏ ɢᴀʏᴀ!\n๏ ᴛᴏᴛᴀʟ ᴠɪᴅᴇᴏs : <code>{total}</code>\n"
        "ᴀʙ /start ᴘᴀʀ ɪɴᴍᴇ sᴇ ʀᴀɴᴅᴏᴍ ᴠɪᴅᴇᴏ ᴀᴀʏᴇɢᴀ."
    )


@app.on_message(filters.command(["delvideo", "delstartvideo", "rmvideo"]) & SUDOERS, group=-2)
async def del_video_cmd(_, message: Message):
    videos = await get_start_videos()
    if not videos:
        return await message.reply_text("❖ ᴋᴏɪ ᴠɪᴅᴇᴏ sᴀᴠᴇᴅ ɴᴀʜɪ ʜᴀɪ.")

    # Reply karke delete
    found = _media_of(message.reply_to_message)
    if found:
        if await delete_start_video(found[0]):
            left = len(await get_start_videos())
            return await message.reply_text(f"🗑 ᴠɪᴅᴇᴏ ᴅᴇʟᴇᴛᴇ ʜᴏ ɢᴀʏᴀ.\n๏ ʙᴀᴄʜᴇ ᴠɪᴅᴇᴏs : <code>{left}</code>")
        return await message.reply_text("❖ ʏᴇ ᴠɪᴅᴇᴏ /start ʟɪsᴛ ᴍᴇ ɴᴀʜɪ ʜᴀɪ.")

    if len(message.command) < 2:
        return await message.reply_text(
            "❖ <b>ᴜsᴀɢᴇ :</b>\n"
            "• <code>/delvideo 2</code> → ɴᴜᴍʙᴇʀ sᴇ (ɴᴜᴍʙᴇʀ /startvideos ᴍᴇ ᴅᴇᴋʜᴏ)\n"
            "• sᴀᴠᴇᴅ ᴠɪᴅᴇᴏ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ <code>/delvideo</code>\n"
            "• <code>/delvideo all</code> → sᴀʙ ᴅᴇʟᴇᴛᴇ"
        )

    arg = message.command[1].lower()
    if arg == "all":
        count = await clear_start_videos()
        return await message.reply_text(f"🗑 sᴀʀᴇ <code>{count}</code> ᴠɪᴅᴇᴏs ᴅᴇʟᴇᴛᴇ ʜᴏ ɢᴀʏᴇ.\nᴀʙ /start ᴘᴀʀ ᴅᴇғᴀᴜʟᴛ ᴍᴇᴅɪᴀ ᴀᴀʏᴇɢᴀ.")

    if not arg.isdigit() or not 1 <= int(arg) <= len(videos):
        return await message.reply_text(f"❖ 1 sᴇ {len(videos)} ᴛᴀᴋ ᴋᴀ ɴᴜᴍʙᴇʀ ᴅᴏ.")

    await delete_start_video(videos[int(arg) - 1]["_id"])
    left = len(await get_start_videos())
    await message.reply_text(f"🗑 ᴠɪᴅᴇᴏ ɴᴏ. {arg} ᴅᴇʟᴇᴛᴇ ʜᴏ ɢᴀʏᴀ.\n๏ ʙᴀᴄʜᴇ ᴠɪᴅᴇᴏs : <code>{left}</code>")


@app.on_message(filters.command(["startvideos", "startsvideos", "startvideo", "startsvideo", "videolist", "videos", "svideos"]) & SUDOERS, group=-2)
async def list_videos_cmd(_, message: Message):
    videos = await get_start_videos()
    if not videos:
        return await message.reply_text("❖ ᴋᴏɪ ᴠɪᴅᴇᴏ sᴀᴠᴇᴅ ɴᴀʜɪ ʜᴀɪ.\nᴠɪᴅᴇᴏ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ /addvideo ʙʜᴇᴊᴏ.")
    lines = [f"<b>❖ /start ᴠɪᴅᴇᴏs ({len(videos)})</b>\n"]
    for i, v in enumerate(videos, 1):
        if v["type"] == "url":
            lines.append(f"{i}. 🔗 {v['media']}")
        else:
            lines.append(f"{i}. 🎬 {v['type']} • ᴀᴅᴅᴇᴅ ʙʏ <code>{v.get('added_by')}</code>")
    lines.append("\n<code>/showvideo 2</code> → ᴅᴇᴋʜᴏ  •  <code>/delvideo 2</code> → ᴅᴇʟᴇᴛᴇ")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


@app.on_message(filters.command(["showvideo"]) & SUDOERS, group=-2)
async def show_video_cmd(client, message: Message):
    videos = await get_start_videos()
    if len(message.command) < 2 or not message.command[1].isdigit() or not 1 <= int(message.command[1]) <= len(videos):
        return await message.reply_text(f"❖ ᴜsᴀɢᴇ : <code>/showvideo 1</code> (ᴛᴏᴛᴀʟ {len(videos)})")
    n = int(message.command[1])
    v = videos[n - 1]
    caption = f"❖ ᴠɪᴅᴇᴏ ɴᴏ. {n}\nᴅᴇʟᴇᴛᴇ : <code>/delvideo {n}</code>"
    try:
        if v["type"] == "animation":
            await message.reply_animation(v["media"], caption=caption)
        else:
            await message.reply_video(v["media"], caption=caption)
    except Exception as e:
        await message.reply_text(f"❖ ᴠɪᴅᴇᴏ ɴᴀʜɪ ʙʜᴇᴊ ᴘᴀʏᴀ : <code>{e}</code>\nɪsᴇ <code>/delvideo {n}</code> sᴇ ʜᴀᴛᴀ ᴅᴏ.")
