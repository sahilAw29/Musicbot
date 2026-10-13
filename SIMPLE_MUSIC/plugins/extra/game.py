# -----------------------------------------------
# YORU MUSIC BOT — Telegram Mini App game launcher
# -----------------------------------------------
import json
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from SIMPLE_MUSIC import app
from config import BANNED_USERS

GAME_MINI_APP_URL = "https://subwaygame-b27tbyed.manus.space"
# Create the BotFather Web App with short name `game`; this deep link makes
# group-chat taps open the Mini App full-screen instead of a normal web page.
GAME_TG_DEEP_LINK = "https://t.me/YoruXmusicbot/game"
GAME_IMAGE = "assets/subway-surfers.jpg"


def _game_markup(message: Message) -> InlineKeyboardMarkup:
    if message.chat.type == "private":
        button = InlineKeyboardButton(
            "▶️ ᴘʟᴀʏ sᴜʙᴡᴀʏ sᴜʀғᴇʀs",
            web_app=WebAppInfo(url=GAME_MINI_APP_URL),
        )
    else:
        # WebApp buttons are intended for private bot chats. For groups use
        # the Telegram t.me Mini App deep link so Telegram opens it full-screen.
        button = InlineKeyboardButton(
            "▶️ ᴘʟᴀʏ sᴜʙᴡᴀʏ sᴜʀғᴇʀs",
            url=GAME_TG_DEEP_LINK,
        )
    return InlineKeyboardMarkup([[button]])


@app.on_message(filters.command(["game", "games"]) & ~BANNED_USERS)
async def game_command(_, message: Message):
    caption = (
        "<blockquote><b>🎮 ɢᴀᴍᴇ ᴢᴏɴᴇ ɪs ʀᴇᴀᴅʏ!</b>\n\n"
        "🏃 <b>sᴜʙᴡᴀʏ sᴜʀғᴇʀs</b>\n"
        "🚆 Dodge trains, collect coins & beat your top run.\n\n"
        "⚡ Tap <b>Play Subway Surfers</b> to open the Telegram Mini App."
        "</blockquote>"
    )
    try:
        await message.reply_photo(photo=GAME_IMAGE, caption=caption, reply_markup=_game_markup(message))
    except Exception:
        await message.reply_text(caption, reply_markup=_game_markup(message))


@app.on_message(filters.private)
async def subway_survival_report(_, message: Message):
    if not message.web_app_data:
        return
    try:
        data = json.loads(message.web_app_data.data or "{}")
        if data.get("type") != "subway_survival":
            return
        seconds = max(0, min(int(data.get("seconds", 0)), 86400))
        minutes, rest = divmod(seconds, 60)
        survived = f"{minutes} min {rest} sec" if minutes else f"{rest} sec"
        await message.reply_text(
            "<blockquote><b>🏃 ʀᴜɴ ʀᴇᴘᴏʀᴛ</b>\n\n"
            f"🎮 <b>sᴜʙᴡᴀʏ sᴜʀғᴇʀs</b>\n"
            f"⏱️ ᴀᴘᴘʀᴏx. sᴜʀᴠɪᴠᴇᴅ : <b>{survived}</b>\n\n"
            "<i>Direct public game session report.</i></blockquote>"
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        await message.reply_text("Run report read nahi ho saka. Mini App se dobara Report my run tap karo.")
