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
import random
import config
from datetime import datetime
from pyrogram import filters, enums
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from config import *
from SIMPLE_MUSIC import app
from SIMPLE_MUSIC.core.call import SIMPLE
from SIMPLE_MUSIC.utils import bot_sys_stats
from SIMPLE_MUSIC.utils.decorators.language import language
from SIMPLE_MUSIC.utils.inline import supp_markup
from config import BANNED_USERS

STYLES = [
    enums.ButtonStyle.PRIMARY,
    enums.ButtonStyle.SUCCESS,
    enums.ButtonStyle.DANGER
]

def _get_style(style_val):
    if getattr(config, "BUTTON_COLOUR", False):
        return {"style": style_val}
    return {}

@app.on_message(filters.command("ping", prefixes=["/"]) & ~BANNED_USERS)
@language
async def ping_com(client, message: Message, _):
    start = datetime.now()
    is_photo = True
    try:
        response = await message.reply_photo(
            config.PING_IMG_URL,
            caption=_["ping_1"].format(app.mention),
        )
    except Exception:
        # PING_IMG_URL kharab ho to text se ping bhejo
        is_photo = False
        response = await message.reply_text(_["ping_1"].format(app.mention))
    try:
        pytgping = await SIMPLE.ping()
    except Exception:
        pytgping = "N/A"
    UP, CPU, RAM, DISK = await bot_sys_stats()
    resp = (datetime.now() - start).microseconds / 1000
    text = _["ping_2"].format(resp, app.mention, UP, RAM, CPU, DISK, pytgping)

    # Photo wale message par edit_text nahi chalta, caption edit karna padta hai
    if is_photo:
        await response.edit_caption(text, reply_markup=supp_markup(_))
    else:
        await response.edit_text(text, reply_markup=supp_markup(_))
