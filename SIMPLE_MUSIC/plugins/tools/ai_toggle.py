# -----------------------------------------------
# /ai on   → bot ke message par reply karne se AI jawab dega
# /ai off  → reply wala AI band
# /ai      → abhi ka status
# Group me: sirf group admin ya bot owner/sudo. DM me: user khud.
# -----------------------------------------------
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import Message

from SIMPLE_MUSIC import app
from SIMPLE_MUSIC.misc import SUDOERS
from SIMPLE_MUSIC.utils.ai_toggle_db import is_ai_on, set_ai


async def _can_toggle(message: Message) -> bool:
    if message.chat.type == ChatType.PRIVATE:
        return True
    user = message.from_user
    if not user:  # anonymous admin
        return bool(message.sender_chat and message.sender_chat.id == message.chat.id)
    if user.id in SUDOERS:
        return True
    try:
        member = await app.get_chat_member(message.chat.id, user.id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


@app.on_message(filters.command(["ai", "chatbot"]), group=-2)
async def ai_toggle_cmd(_, message: Message):
    chat_id = message.chat.id
    arg = message.command[1].lower() if len(message.command) > 1 else ""

    if arg not in ("on", "off", "enable", "disable"):
        state = "ᴏɴ ✅" if await is_ai_on(chat_id) else "ᴏғғ ❌"
        return await message.reply_text(
            f"❖ <b>ᴀɪ ʀᴇᴘʟʏ ᴄʜᴀᴛ :</b> {state}\n\n"
            "• <code>/ai on</code> → ʙᴏᴛ ᴋᴇ ᴍsɢ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴏ ᴛᴏ ᴀɪ ᴊᴀᴡᴀʙ ᴅᴇɢᴀ\n"
            "• <code>/ai off</code> → ᴀɪ ʀᴇᴘʟʏ ʙᴀɴᴅ"
        )

    if not await _can_toggle(message):
        return await message.reply_text("❖ ʏᴇ ᴄᴏᴍᴍᴀɴᴅ sɪʀғ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs ᴜsᴇ ᴋᴀʀ sᴀᴋᴛᴇ ʜᴀɪɴ.")

    turn_on = arg in ("on", "enable")
    await set_ai(chat_id, turn_on)
    if turn_on:
        await message.reply_text("✅ <b>ᴀɪ ᴏɴ ʜᴏ ɢᴀʏᴀ!</b>\nᴀʙ ᴍᴇʀᴇ ᴍᴇssᴀɢᴇ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴏɢᴇ ᴛᴏ ᴍᴀɪɴ ᴊᴀᴡᴀʙ ᴅᴜɴɢɪ.")
    else:
        await message.reply_text("❌ <b>ᴀɪ ᴏғғ ʜᴏ ɢᴀʏᴀ!</b>\nᴀʙ ʀᴇᴘʟʏ ᴋᴀʀɴᴇ ᴘᴀʀ ᴍᴀɪɴ ᴊᴀᴡᴀʙ ɴᴀʜɪ ᴅᴜɴɢɪ.")
