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
from pyrogram import filters
from pyrogram.types import Message

from SIMPLE_MUSIC import app
from SIMPLE_MUSIC.core.call import SIMPLE

close = 30


# video_chat_started must not stop anything: the assistant starts the VC itself
# when it plays, so that message would end the song it just began.
@app.on_message(filters.video_chat_ended, group=close)
async def video_chat_closed(_, message: Message):
    await SIMPLE.stop_stream_force(message.chat.id)
