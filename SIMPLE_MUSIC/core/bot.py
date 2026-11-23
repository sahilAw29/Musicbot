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
import os
import sys
from pyrogram import Client, errors
from pyrogram.enums import ChatMemberStatus, ParseMode
import config
from ..logging import LOGGER

# saved clone session kharab hone wale errors (pyrogram version ke hisaab se)
_BAD_SESSION = tuple(
    c for c in (getattr(errors, "Unauthorized", None), getattr(errors, "AuthKeyDuplicated", None)) if c
)


class SIMPLE(Client):
    def __init__(self):
        LOGGER(__name__).info(f"Starting Bot...")
        # clone bot: pichli baar ka login session (har restart par naya login nahi karna padta)
        self._clone_session = os.getenv("CLONE_BOT_SESSION", "") if getattr(config, "IS_CLONE_BOT", False) else ""
        extra = {"session_string": self._clone_session} if self._clone_session else {}
        super().__init__(
            name="YORU_MUSIC_BOT",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            in_memory=True,
            max_concurrent_transmissions=7,
            parse_mode=ParseMode.HTML,
            **extra,
        )

    async def start(self):
        # Retry on FloodWait (too many redeploys can trigger Telegram rate limit)
        # aur Telegram login timeout par bhi crash nahi, thoda ruk ke dobara try
        tries = 0
        while True:
            try:
                await super().start()
                break
            except _BAD_SESSION as e:
                if not self._clone_session:
                    raise
                # saved session kharab → hata do, agli baar token se fresh login
                LOGGER(__name__).warning(f"Clone saved session invalid ({e}), token se dobara login hoga")
                await self._save_clone_session("")
                sys.exit(3)
            except errors.FloodWait as e:
                wait_sec = e.value + 5
                LOGGER(__name__).warning(
                    f"Telegram FloodWait: Waiting {wait_sec} seconds before retrying..."
                )
                await asyncio.sleep(wait_sec)
            except (TimeoutError, asyncio.TimeoutError, OSError, ConnectionError) as e:
                tries += 1
                if tries > 20:
                    raise
                wait_sec = min(30 * tries, 300)
                LOGGER(__name__).warning(
                    f"Telegram login timeout ({type(e).__name__}), {wait_sec}s baad dobara try ({tries}/20)..."
                )
                try:
                    await self.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(wait_sec)

        self.id = self.me.id
        self.name = self.me.first_name + " " + (self.me.last_name or "")
        self.username = self.me.username
        self.mention = self.me.mention

        if getattr(config, "IS_CLONE_BOT", False):
            # clone bot ko log group ki zaroorat nahi — seedha chalu
            if not self._clone_session:
                try:
                    await self._save_clone_session(await self.export_session_string())
                except Exception as e:
                    LOGGER(__name__).warning(f"Clone session save failed: {e}")
            LOGGER(__name__).info(f"Clone Bot Started as {self.name}")
            return

        try:
            await self.send_message(
                chat_id=config.LOGGER_ID,
                text=f"<u><b>» {self.mention} ʙᴏᴛ sᴛᴀʀᴛᴇᴅ :</b><u>\n\nɪᴅ : <code>{self.id}</code>\nɴᴀᴍᴇ : {self.name}\nᴜsᴇʀɴᴀᴍᴇ : @{self.username}",
            )
        except (errors.ChannelInvalid, errors.PeerIdInvalid):
            LOGGER(__name__).error(
                "Bot has failed to access the log group/channel. Make sure that you have added your bot to your log group/channel."
            )
            exit()
        except Exception as ex:
            LOGGER(__name__).error(
                f"Bot has failed to access the log group/channel.\n  Reason : {type(ex).__name__}."
            )
            exit()

        a = await self.get_chat_member(config.LOGGER_ID, self.id)
        if a.status != ChatMemberStatus.ADMINISTRATOR:
            LOGGER(__name__).error(
                "Please promote your bot as an admin in your log group/channel."
            )
            exit()
        LOGGER(__name__).info(f"Yoru Music Bot Started as {self.name}")

    async def _save_clone_session(self, value):
        from SIMPLE_MUSIC.core.mongo import mongodb
        token = getattr(config, "BOT_TOKEN", "")
        await mongodb.clonebots.update_one({"token": token}, {"$set": {"bot_session": value}})

    async def stop(self):
        await super().stop()
