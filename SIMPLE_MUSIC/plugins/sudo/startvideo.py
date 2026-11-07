# -----------------------------------------------
# /start random video — owner/sudo commands
#
#  /addvideo        → kisi video/GIF par reply karke bhejo (ya /addvideo <link>)
#  /delvideo 2      → list ka 2 number wala video delete
#  /delvideo        → kisi saved video par reply karke bhi delete hota hai
#  /delvideo all    → saare video delete (fir START_IMG_URL wapas chalega)
#  /startvideos     → saare saved video ki list
#  /showvideo 2     → 2 number wala video dekh lo
# -----------------------------------------------
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
    """(unique_key, file_id, type) ya None."""
    if not msg:
        return None
    if msg.video:
        return msg.video.file_unique_id, msg.video.file_id, "video"
    if msg.animation:
        return msg.animation.file_unique_id, msg.animation.file_id, "animation"
    return None


@app.on_message(filters.command(["addvideo", "addstartvideo"]) & SUDOERS)
async def add_video_cmd(_, message: Message):
    found = _media_of(message.reply_to_message)

    if not found and len(message.command) > 1:
        link = message.text.split(None, 1)[1].strip()
        if link.startswith("http"):
            found = link, link, "url"

    if not found:
        if message.reply_to_message and message.reply_to_message.document:
            return await message.reply_text(
                "❖ ʏᴇ ғɪʟᴇ ʜᴀɪ, ᴠɪᴅᴇᴏ ɴᴀʜɪ.\nᴠɪᴅᴇᴏ ᴋᴏ ɴᴏʀᴍᴀʟ ᴠɪᴅᴇᴏ ᴋɪ ᴛᴀʀᴀʜ ʙʜᴇᴊᴏ (ғɪʟᴇ ᴍᴀᴛ ʙɴᴀᴏ), ғɪʀ ʀᴇᴘʟʏ ᴋᴀʀᴏ."
            )
        return await message.reply_text(
            "❖ <b>ᴜsᴀɢᴇ :</b>\n"
            "• ᴋɪsɪ ᴠɪᴅᴇᴏ/ɢɪғ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ <code>/addvideo</code>\n"
            "• ʏᴀ <code>/addvideo https://files.catbox.moe/xyz.mp4</code>"
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


@app.on_message(filters.command(["delvideo", "delstartvideo", "rmvideo"]) & SUDOERS)
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


@app.on_message(filters.command(["startvideos", "videolist"]) & SUDOERS)
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


@app.on_message(filters.command(["showvideo"]) & SUDOERS)
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
