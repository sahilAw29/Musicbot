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
_FAILS = {}       # bot_id -> lagatar kitni baar start hote hi band hua

# clone ki apni settings: key -> (db field, env var, naam). Khali ho to main bot wali.
CLONE_FIELDS = {
    "channel": ("support_channel", "SUPPORT_CHANNEL", "ᴄʜᴀɴɴᴇʟ ʟɪɴᴋ"),
    "support": ("support_chat", "SUPPORT_CHAT", "sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ ʟɪɴᴋ"),
    "owner": ("owner_btn_id", "OWNER_BUTTON_ID", "ᴏᴡɴᴇʀ ɪᴅ"),
    "log": ("log_group_id", "LOGGER_ID", "ʟᴏɢ ɢʀᴏᴜᴘ ɪᴅ"),
    "bcast": ("broadcast_admin", "BROADCAST_ADMINS", "ʙʀᴏᴀᴅᴄᴀsᴛ ᴀᴅᴍɪɴ ɪᴅ"),
}


def clone_value(doc, key):
    """(value, default hai ya nahi)"""
    field, env, _ = CLONE_FIELDS[key]
    if doc.get(field):
        return str(doc[field]), False
    main = {"channel": config.SUPPORT_CHANNEL, "support": config.SUPPORT_CHAT,
            "owner": getattr(config, "OWNER_BUTTON_ID", config.OWNER_ID),
            "log": config.LOGGER_ID,
            "bcast": "sɪʀғ sᴜᴅᴏ"}[key]
    return str(main), True


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
class _BotInfo:
    def __init__(self, data):
        self.id = data["id"]
        self.username = data.get("username") or ""
        self.first_name = data.get("first_name") or ""


async def _check_token(token):
    """Bot API (getMe) se check — naya MTProto login nahi karna padta, timeout nahi aata."""
    import aiohttp
    url = f"https://api.telegram.org/bot{token}/getMe"
    last = None
    for _ in range(3):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    data = await r.json(content_type=None)
            if data.get("ok"):
                return _BotInfo(data["result"])
            raise ValueError(data.get("description") or "token galat hai ya revoke ho gaya")
        except ValueError:
            raise
        except Exception as e:
            last = e
            await asyncio.sleep(3)
    raise ValueError(f"Telegram se check nahi ho paya: {last}")


async def _check_string(string):
    c = Client(f"clchk_{uuid.uuid4().hex[:8]}", api_id=config.API_ID, api_hash=config.API_HASH,
               session_string=string, in_memory=True, no_updates=True)
    try:
        await asyncio.wait_for(c.start(), 90)
        return c.me
    finally:
        try:
            await c.stop()
        except Exception:
            pass


def _main_strings():
    return {s for s in (getattr(config, f"STRING{i}", None) for i in range(1, 8)) if s}


# ───────────────────── start media clones ke liye ─────────────────────
from SIMPLE_MUSIC.utils.clone_media import export_media


async def _export_loop():
    """Clones hain to har 2 min me naya saved media disk par (clone wahan se upload karega)."""
    while True:
        await asyncio.sleep(120)
        try:
            if await _col().count_documents({}):
                await export_media()
        except Exception as e:
            log.warning(f"clone media export failed: {e}")


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
    try:
        await asyncio.wait_for(export_media(), 300)
    except Exception as e:
        log.warning(f"clone media export failed: {e}")
    env = os.environ.copy()
    env.update({
        "BOT_TOKEN": doc["token"],
        "STRING_SESSION": doc["string"],
        "CLONE_BOT_SESSION": doc.get("bot_session") or "",
        "BOT_USERNAME": doc.get("username") or "",
        "ASSUSERNAME": doc.get("ass_username") or "",
        "IS_CLONE_BOT": "1",
        "CLONE_PARENT_PID": str(os.getpid()),
        "PORT": "0",  # health server ka port main bot se na takraye
        "PYTHONUNBUFFERED": "1",
    })
    # clone ki apni channel / support / owner button (warna main bot wali)
    for _key, (_field, _env, _) in CLONE_FIELDS.items():
        if doc.get(_field):
            env[_env] = str(doc[_field])
    env["CLONE_CUSTOM_LOG"] = "1" if doc.get("log_group_id") else ""
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
    if code == 4:
        _FAILS.pop(bot_id, None)
        await _col().update_one({"bot_id": bot_id}, {"$set": {"enabled": False, "bot_session": ""}})
        await _notify(
            f"⚠️ <b>ᴄʟᴏɴᴇ @{doc.get('username')} ʟᴏɢɪɴ ɴᴀʜɪ ʜᴏ ʀᴀʜᴀ</b>\n\n"
            "Telegram is bot ka login baar baar timeout kar raha hai (bahut zyada login ho chuke).\n"
            "Fix: @BotFather → /revoke → is bot ka naya token lo → /admins → Cʟᴏɴᴇ Bᴏᴛ → ➕ Naya Clone "
            "me naya token + wahi string daalo."
        )
        return
    if time.time() - started < 120:
        # shuru hote hi band ho gaya → 3 baar ruk ke dobara try, phir band
        fails = _FAILS.get(bot_id, 0) + 1
        _FAILS[bot_id] = fails
        if fails <= 3:
            log.warning(f"Clone {bot_id} start failed (code {code}), {90 * fails}s baad retry {fails}/3")
            await asyncio.sleep(90 * fails)
            fresh = await _col().find_one({"bot_id": bot_id})
            if fresh and fresh.get("enabled", True) and bot_id not in _STOPPING:
                await _spawn(fresh)
            return
        _FAILS.pop(bot_id, None)
        await _col().update_one({"bot_id": bot_id}, {"$set": {"enabled": False}})
        await _notify(f"❌ <b>ᴄʟᴏɴᴇ @{doc.get('username')} ʙᴀɴᴅ ʜᴏ ɢᴀʏᴀ</b> (code {code})\n"
                      f"<pre>{_esc(_tail(bot_id))}</pre>\n"
                      f"/admins → ᴄʟᴏɴᴇ ʙᴏᴛ sᴇ ʀᴇsᴛᴀʀᴛ ᴋᴀʀ sᴀᴋᴛᴇ ʜᴏ.")
        return
    _FAILS.pop(bot_id, None)
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
    # pehle se chal raha clone ho to band karo, warna string do jagah chalegi (AUTH_KEY_DUPLICATED)
    for d in await _all_clones():
        if d["bot_id"] != bot_me.id and d.get("string") == string:
            return await wait.edit_text(f"❌ ʏᴇ sᴛʀɪɴɢ ᴘᴇʜʟᴇ sᴇ @{d.get('username')} ᴍᴇ ʟᴀɢɪ ʜᴀɪ.")
    await _stop(bot_me.id)
    await asyncio.sleep(3)
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
        "bot_session": "",  # naya token → pehli baar fresh login
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


def start_set_flow(user_id, key, bot_id):
    _pending[user_id] = {"step": "set", "key": key, "bot_id": bot_id}
    name = CLONE_FIELDS[key][2]
    if key == "owner":
        hint = "ɴᴀʏᴀ <b>ᴏᴡɴᴇʀ ᴜsᴇʀ ɪᴅ</b> ʙʜᴇᴊᴏ (sɪʀғ ɴᴜᴍʙᴇʀ, ᴊᴀɪsᴇ <code>123456789</code>)."
    elif key == "log":
        hint = ("ʟᴏɢ ɢʀᴏᴜᴘ ᴋɪ <b>ᴄʜᴀᴛ ɪᴅ</b> ʙʜᴇᴊᴏ (ᴊᴀɪsᴇ <code>-1001234567890</code>).\n"
                "⚠️ ᴘᴇʜʟᴇ ᴄʟᴏɴᴇ ʙᴏᴛ ᴋᴏ ᴜs ɢʀᴏᴜᴘ ᴍᴇ <b>ᴀᴅᴍɪɴ</b> ʙᴀɴᴀᴏ ᴀᴜʀ ᴀssɪsᴛᴀɴᴛ ᴋᴏ ᴀᴅᴅ ᴋᴀʀᴏ.")
    elif key == "bcast":
        hint = ("ᴊɪsᴇ ɪs ᴄʟᴏɴᴇ ᴍᴇ <b>/broadcast</b> ᴋᴀʀɴᴇ ᴅᴇɴᴀ ʜᴀɪ ᴜsᴋᴀ <b>ᴜsᴇʀ ɪᴅ</b> ʙʜᴇᴊᴏ.\n"
                "ᴢʏᴀᴅᴀ ʜᴏɴ ᴛᴏ sᴘᴀᴄᴇ sᴇ: <code>111 222</code>")
    else:
        hint = f"ɴᴀʏᴀ <b>{name}</b> ʙʜᴇᴊᴏ (<code>https://t.me/...</code>)."
    return (f"✏️ {hint}\n\nᴍᴀɪɴ ʙᴏᴛ ᴡᴀʟᴀ ᴡᴀᴘᴀs ʟᴀɢᴀɴᴀ ʜᴏ ᴛᴏ <code>default</code> ʙʜᴇᴊᴏ.\n"
            "ᴄᴀɴᴄᴇʟ : /cancel")


async def _apply_setting(message, state, text):
    key, bot_id = state["key"], state["bot_id"]
    field, _, name = CLONE_FIELDS[key]
    value = text.strip()
    if value.lower() == "default":
        value = ""
    elif key == "owner":
        if not value.isdigit():
            return await app.send_message(message.chat.id, "❌ sɪʀғ ɴᴜᴍʙᴇʀ ᴡᴀʟᴀ ᴜsᴇʀ ɪᴅ ʙʜᴇᴊᴏ. ᴅᴏʙᴀʀᴀ ʏᴀ /cancel"), False
        value = int(value)
    elif key == "log":
        if not re.match(r"^-\d{6,}$", value):
            return await app.send_message(message.chat.id, "❌ ɢʀᴏᴜᴘ ᴄʜᴀᴛ ɪᴅ <code>-100</code> sᴇ sʜᴜʀᴜ ʜᴏᴛɪ ʜᴀɪ. ᴅᴏʙᴀʀᴀ ʏᴀ /cancel"), False
        value = int(value)
    elif key == "bcast":
        ids = value.replace(",", " ").split()
        if not ids or not all(i.isdigit() for i in ids):
            return await app.send_message(message.chat.id, "❌ sɪʀғ ɴᴜᴍʙᴇʀ ᴡᴀʟᴇ ᴜsᴇʀ ɪᴅ ʙʜᴇᴊᴏ. ᴅᴏʙᴀʀᴀ ʏᴀ /cancel"), False
        value = " ".join(ids)
    elif not re.match(r"^https?://\S+$", value):
        return await app.send_message(message.chat.id, "❌ ʟɪɴᴋ <code>https://</code> sᴇ sʜᴜʀᴜ ʜᴏɴᴀ ᴄʜᴀʜɪʏᴇ. ᴅᴏʙᴀʀᴀ ʏᴀ /cancel"), False
    await _col().update_one({"bot_id": bot_id}, {"$set": {field: value}})
    d = await restart_clone(bot_id)
    shown = value if value != "" else "ᴍᴀɪɴ ʙᴏᴛ ᴡᴀʟᴀ (ᴅᴇғᴀᴜʟᴛ)"
    await app.send_message(
        message.chat.id,
        f"✅ @{(d or {}).get('username')} ᴋᴀ {name} sᴇᴛ : <code>{shown}</code>\n"
        "ᴄʟᴏɴᴇ ʀᴇsᴛᴀʀᴛ ʜᴏ ʀᴀʜᴀ ʜᴀɪ, 1 ᴍɪɴᴜᴛᴇ ᴍᴇ ɴᴀʏᴀ ᴅɪᴋʜᴇɢᴀ.",
    )
    return None, True


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
    _FAILS.pop(bot_id, None)
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
        if state["step"] == "set":
            _, done = await _apply_setting(message, state, text)
            if done:
                _pending.pop(message.from_user.id, None)
            message.stop_propagation()
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
                await asyncio.sleep(20)  # ek saath saare login na ho

    try:
        asyncio.get_event_loop().create_task(_autostart())
        asyncio.get_event_loop().create_task(_export_loop())
    except Exception as e:
        log.error(f"Clone autostart schedule failed: {e}")
