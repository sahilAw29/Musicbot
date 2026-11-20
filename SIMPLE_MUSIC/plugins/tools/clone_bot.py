# -----------------------------------------------
# Clone Bot — /admins → "Cʟᴏɴᴇ Bᴏᴛ"
# Bot token + string session do, same to same bot (sab commands, settings,
# database, owner) ek alag process me chalu ho jata hai.
#
# Sab management /admins → Cʟᴏɴᴇ Bᴏᴛ se (naya clone, list, restart, delete).
# Sirf .env ke OWNER_ID ke liye.
# -----------------------------------------------
import asyncio
import os
import re
import sys
import threading
import time
import uuid

import config
from pyrogram import Client, filters
from pyrogram.types import Message

from SIMPLE_MUSIC import LOGGER, app

log = LOGGER(__name__)

ADMINS = config.PANEL_ADMINS
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LOG_DIR = os.path.join(ROOT_DIR, "clone_logs")
TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")

_RUNNING = {}     # bot_id -> asyncio Process
_STOPPING = set() # bot_ids jinko jaan-boojh kar band kiya
_pending = {}     # user_id -> {"step": "token"/"string", "token": ...}


# ───────────────────── clone ke andar: parent mare to clone bhi band ─────────────────────
if config.IS_CLONE_BOT:
    _parent = int(os.getenv("CLONE_PARENT_PID", "0") or 0)

    def _watch_parent():
        while True:
            time.sleep(5)
            if _parent and os.getppid() != _parent:
                os._exit(0)

    threading.Thread(target=_watch_parent, daemon=True).start()


# ───────────────────── database ─────────────────────
def _col():
    from SIMPLE_MUSIC.core.mongo import mongodb
    return mongodb.clonebots


async def _all_clones():
    return [d async for d in _col().find({})]


# ───────────────────── checks ─────────────────────
async def _check_token(token):
    c = Client(f"clchk_{uuid.uuid4().hex[:8]}", api_id=config.API_ID, api_hash=config.API_HASH,
               bot_token=token, in_memory=True, no_updates=True)
    await asyncio.wait_for(c.start(), 60)
    me = c.me
    try:
        await c.stop()
    except Exception:
        pass
    return me


async def _check_string(string):
    c = Client(f"clchk_{uuid.uuid4().hex[:8]}", api_id=config.API_ID, api_hash=config.API_HASH,
               session_string=string, in_memory=True, no_updates=True)
    await asyncio.wait_for(c.start(), 60)
    me = c.me
    try:
        await c.stop()
    except Exception:
        pass
    return me


def _main_strings():
    return {s for s in (getattr(config, f"STRING{i}", None) for i in range(1, 8)) if s}


# ───────────────────── process ─────────────────────
def _log_path(bot_id):
    return os.path.join(LOG_DIR, f"{bot_id}.log")


def _tail(bot_id, lines=15):
    try:
        with open(_log_path(bot_id), "r", errors="ignore") as f:
            return "".join(f.readlines()[-lines:])[-3000:]
    except Exception:
        return ""


async def _spawn(doc):
    bot_id = doc["bot_id"]
    old = _RUNNING.get(bot_id)
    if old and old.returncode is None:
        return old
    os.makedirs(LOG_DIR, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "BOT_TOKEN": doc["token"],
        "STRING_SESSION": doc["string"],
        "BOT_USERNAME": doc.get("username") or "",
        "ASSUSERNAME": doc.get("ass_username") or "",
        "IS_CLONE_BOT": "1",
        "CLONE_PARENT_PID": str(os.getpid()),
        "PORT": "0",  # health server ka port main bot se na takraye
        "PYTHONUNBUFFERED": "1",
    })
    # main bot ke baaki assistants clone me na chale (warna session duplicate ho jata hai)
    for i in range(2, 8):
        env[f"STRING_SESSION{i}"] = ""
    logf = open(_log_path(bot_id), "w")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "SIMPLE_MUSIC",
        cwd=ROOT_DIR, env=env, stdout=logf, stderr=asyncio.subprocess.STDOUT,
    )
    logf.close()
    _RUNNING[bot_id] = proc
    _STOPPING.discard(bot_id)
    asyncio.create_task(_watch(doc, proc, time.time()))
    return proc


async def _watch(doc, proc, started):
    bot_id = doc["bot_id"]
    code = await proc.wait()
    if _RUNNING.get(bot_id) is proc:
        _RUNNING.pop(bot_id, None)
    if bot_id in _STOPPING:
        return
    if time.time() - started < 120:
        # shuru hote hi band ho gaya → galti hai, baar baar restart nahi karenge
        await _col().update_one({"bot_id": bot_id}, {"$set": {"enabled": False}})
        await _notify(f"❌ <b>ᴄʟᴏɴᴇ @{doc.get('username')} ʙᴀɴᴅ ʜᴏ ɢᴀʏᴀ</b> (code {code})\n"
                      f"<pre>{_esc(_tail(bot_id))}</pre>\n"
                      f"/admins → ᴄʟᴏɴᴇ ʙᴏᴛ sᴇ ʀᴇsᴛᴀʀᴛ ᴋᴀʀ sᴀᴋᴛᴇ ʜᴏ.")
        return
    log.warning(f"Clone {bot_id} crashed (code {code}), restarting in 15s")
    await asyncio.sleep(15)
    fresh = await _col().find_one({"bot_id": bot_id})
    if fresh and fresh.get("enabled", True) and bot_id not in _STOPPING:
        await _spawn(fresh)


async def _stop(bot_id):
    _STOPPING.add(bot_id)
    proc = _RUNNING.pop(bot_id, None)
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 10)
        except asyncio.TimeoutError:
            proc.kill()


async def _wait_started(bot_id, timeout=150):
    """True = chalu, False = band ho gaya, None = abhi tak pata nahi."""
    end = time.time() + timeout
    while time.time() < end:
        await asyncio.sleep(4)
        proc = _RUNNING.get(bot_id)
        if proc is None or proc.returncode is not None:
            return False
        if "Bot Started as" in _tail(bot_id, 200):
            return True
    return None


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _notify(text):
    for uid in ADMINS:
        try:
            await app.send_message(uid, text)
            return
        except Exception:
            pass
    try:
        await app.send_message(config.LOGGER_ID, text)
    except Exception:
        pass


# ───────────────────── clone banana ─────────────────────
async def _do_clone(message: Message, token: str, string: str):
    token, string = token.strip(), string.strip()
    if not TOKEN_RE.match(token):
        return await app.send_message(message.chat.id, "❌ ʙᴏᴛ ᴛᴏᴋᴇɴ ɢᴀʟᴀᴛ ʜᴀɪ. @BotFather sᴇ ᴘᴜʀᴀ ᴛᴏᴋᴇɴ ᴄᴏᴘʏ ᴋᴀʀᴏ.")
    if token == config.BOT_TOKEN:
        return await app.send_message(message.chat.id, "❌ ʏᴇ ᴛᴏ ᴍᴀɪɴ ʙᴏᴛ ᴋᴀ ᴛᴏᴋᴇɴ ʜᴀɪ. ɴᴀʏᴀ ʙᴏᴛ ʙᴀɴᴀᴏ @BotFather sᴇ.")
    if string in _main_strings():
        return await app.send_message(message.chat.id, "❌ ʏᴇ sᴛʀɪɴɢ ᴍᴀɪɴ ʙᴏᴛ ᴋᴀ ᴀssɪsᴛᴀɴᴛ ʜᴀɪ. ᴅᴜsʀɪ ɪᴅ ᴋɪ sᴛʀɪɴɢ ᴅᴏ.")

    wait = await app.send_message(message.chat.id, "⏳ ᴛᴏᴋᴇɴ ᴀᴜʀ sᴛʀɪɴɢ ᴄʜᴇᴄᴋ ʜᴏ ʀᴀʜᴇ ʜᴀɪɴ...")
    try:
        bot_me = await _check_token(token)
    except Exception as e:
        return await wait.edit_text(f"❌ ʙᴏᴛ ᴛᴏᴋᴇɴ ɴᴀʜɪ ᴄʜᴀʟᴀ : <code>{_esc(str(e))}</code>")
    try:
        ass_me = await _check_string(string)
    except Exception as e:
        return await wait.edit_text(f"❌ sᴛʀɪɴɢ sᴇssɪᴏɴ ɴᴀʜɪ ᴄʜᴀʟɪ : <code>{_esc(str(e))}</code>")
    if ass_me.is_bot:
        return await wait.edit_text("❌ sᴛʀɪɴɢ ᴋɪsɪ ᴜsᴇʀ ɪᴅ ᴋɪ ʜᴏɴɪ ᴄʜᴀʜɪʏᴇ, ʙᴏᴛ ᴋɪ ɴᴀʜɪ.")

    for d in await _all_clones():
        if d["bot_id"] != bot_me.id and d.get("string") == string:
            return await wait.edit_text(f"❌ ʏᴇ sᴛʀɪɴɢ ᴘᴇʜʟᴇ sᴇ @{d.get('username')} ᴍᴇ ʟᴀɢɪ ʜᴀɪ.")

    doc = {
        "bot_id": bot_me.id,
        "username": bot_me.username,
        "token": token,
        "string": string,
        "ass_id": ass_me.id,
        "ass_username": ass_me.username or "",
        "added_by": message.from_user.id,
        "added_on": int(time.time()),
        "enabled": True,
    }
    await _stop(bot_me.id)  # agar pehle se tha to naye token/string se dobara
    await _col().update_one({"bot_id": bot_me.id}, {"$set": doc}, upsert=True)
    await _spawn(doc)
    await wait.edit_text(
        f"🚀 <b>@{bot_me.username}</b> sᴛᴀʀᴛ ʜᴏ ʀᴀʜᴀ ʜᴀɪ...\n"
        f"ᴀssɪsᴛᴀɴᴛ : {ass_me.mention}"
    )
    ok = await _wait_started(bot_me.id)
    if ok:
        await wait.edit_text(
            f"✅ <b>ᴄʟᴏɴᴇ ʀᴇᴀᴅʏ!</b>\n\nʙᴏᴛ : @{bot_me.username}\nᴀssɪsᴛᴀɴᴛ : {ass_me.mention}\n\n"
            f"sᴀʙ ᴋᴜᴄʜ ᴍᴀɪɴ ʙᴏᴛ ᴊᴀɪsᴀ ʜɪ ʜᴀɪ. ᴍᴀɴᴀɢᴇ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ /admins → ᴄʟᴏɴᴇ ʙᴏᴛ"
        )
    elif ok is None:
        await wait.edit_text(f"⏳ @{bot_me.username} ᴀʙʜɪ sᴛᴀʀᴛ ʜᴏ ʀᴀʜᴀ ʜᴀɪ, ᴛʜᴏᴅɪ ᴅᴇʀ ʙᴀᴀᴅ /admins → ᴄʟᴏɴᴇ ʙᴏᴛ ᴅᴇᴋʜᴏ.")
    # ok False → _watch() khud error bhej dega


# ───────────────────── /admins panel ke liye helpers ─────────────────────
ADMIN_FILTER = filters.user(ADMINS)

ASK_TOKEN = ("🤖 <b>sᴛᴇᴘ 1/2</b>\n\nɴᴀʏᴇ ʙᴏᴛ ᴋᴀ <b>ʙᴏᴛ ᴛᴏᴋᴇɴ</b> ʙʜᴇᴊᴏ (@BotFather sᴇ).\n"
             "ᴄᴀɴᴄᴇʟ : /cancel")
ASK_STRING = ("🔑 <b>sᴛᴇᴘ 2/2</b>\n\nᴀʙ ᴀssɪsᴛᴀɴᴛ ᴋɪ <b>sᴛʀɪɴɢ sᴇssɪᴏɴ</b> ʙʜᴇᴊᴏ.\n"
              "ᴄᴀɴᴄᴇʟ : /cancel")


def start_clone_flow(user_id):
    _pending[user_id] = {"step": "token"}


def is_running(bot_id):
    proc = _RUNNING.get(bot_id)
    return bool(proc and proc.returncode is None)


async def list_clones():
    return await _all_clones()


async def get_clone(bot_id):
    return await _col().find_one({"bot_id": bot_id})


async def restart_clone(bot_id):
    d = await get_clone(bot_id)
    if not d:
        return None
    await _stop(bot_id)
    d["enabled"] = True
    await _col().update_one({"bot_id": bot_id}, {"$set": {"enabled": True}})
    await _spawn(d)
    return d


async def delete_clone(bot_id):
    d = await get_clone(bot_id)
    await _stop(bot_id)
    await _col().delete_one({"bot_id": bot_id})
    return d


if not config.IS_CLONE_BOT:

    @app.on_message(filters.command("cancel") & filters.private & ADMIN_FILTER, group=-3)
    async def clone_cancel(_, message: Message):
        if _pending.pop(message.from_user.id, None):
            await message.reply_text("✖ ᴄʟᴏɴᴇ ᴄᴀɴᴄᴇʟ.")
            message.stop_propagation()

    @app.on_message(filters.private & filters.text & ADMIN_FILTER & ~filters.regex(r"^/"), group=-3)
    async def clone_input(_, message: Message):
        state = _pending.get(message.from_user.id)
        if not state:
            return
        text = message.text.strip()
        try:
            await message.delete()  # token/string chat me na rahe
        except Exception:
            pass
        if state["step"] == "token":
            if not TOKEN_RE.match(text):
                await app.send_message(message.chat.id, "❌ ʏᴇ ʙᴏᴛ ᴛᴏᴋᴇɴ ɴᴀʜɪ ʟᴀɢ ʀᴀʜᴀ. ᴅᴏʙᴀʀᴀ ʙʜᴇᴊᴏ ʏᴀ /cancel")
            else:
                state.update(step="string", token=text)
                await app.send_message(message.chat.id, ASK_STRING)
        else:
            _pending.pop(message.from_user.id, None)
            asyncio.create_task(_do_clone(message, state["token"], text))
        message.stop_propagation()

    # main bot ke start hone par saare saved clones apne aap chalu
    async def _autostart():
        await asyncio.sleep(20)
        try:
            docs = await _all_clones()
        except Exception as e:
            return log.error(f"Clone autostart failed: {e}")
        for d in docs:
            if d.get("enabled", True):
                try:
                    await _spawn(d)
                    log.info(f"Clone @{d.get('username')} started")
                except Exception as e:
                    log.error(f"Clone @{d.get('username')} start failed: {e}")
                await asyncio.sleep(5)

    try:
        asyncio.get_event_loop().create_task(_autostart())
    except Exception as e:
        log.error(f"Clone autostart schedule failed: {e}")
