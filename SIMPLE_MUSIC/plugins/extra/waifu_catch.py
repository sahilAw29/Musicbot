# -----------------------------------------------
# 🔸 YORU MUSIC BOT Project
# 🔹 Catch-Your-Waifu system (spawn / guess / harem / gift / trade / top)
#
# Kaise kaam karta hai:
#   • Group me har N messages (default 50) ke baad ek character spawn hota hai
#   • Photo + caption aata hai: anime ka naam + character ka naam (kuch word/letter hidden)
#   • Jo pehle exact poora naam /guess ya image reply me likhega, character uske harem me jayega
# -----------------------------------------------
import asyncio
import html
import io
import json
import os
import random
import re
import time
from urllib.parse import urljoin

import aiohttp
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from SIMPLE_MUSIC import app
from SIMPLE_MUSIC.logging import LOGGER
from SIMPLE_MUSIC.misc import SUDOERS
from SIMPLE_MUSIC.mongo import waifu_db as wdb

try:
    from unidecode import unidecode
except Exception:  # unidecode na ho to bhi chale
    def unidecode(x):
        return x

log = LOGGER(__name__)

# ---------------- settings (.env se change kar sakte ho) ----------------
WAIFU_API = os.getenv("WAIFU_API", "http://192.46.208.170:7856/rgb/anime")
DEFAULT_FREQ = int(os.getenv("WAIFU_SPAWN_FREQ", 50))    # kitne messages baad spawn
FLEE_TIME = int(os.getenv("WAIFU_FLEE_TIME", 600))       # sec, 0 = kabhi nahi bhagega
MIN_FREQ = 20                                             # group admins ke liye minimum
HAREM_PER_PAGE = 8
SPAM_STREAK = 8                                           # ek hi user lagatar itne msg kare to count nahi hoga

RARITIES = [
    # (naam, emoji, weight, coins)
    ("Common", "⚪️", 50, 10),
    ("Rare", "🔵", 28, 25),
    ("Legendary", "⭐️", 14, 50),
    ("Mythic", "🔥", 6, 100),
    ("Limited", "💎", 2, 250),
]
RARITY_EMOJI = {r[0].lower(): r[1] for r in RARITIES}
RARITY_COINS = {r[0].lower(): r[3] for r in RARITIES}

# Premium/custom emoji palette. Telegram clients that cannot render custom
# emoji still show the Unicode fallback inside each tag.
PE = {
    "flower": "<emoji id='5222044641200720562'>🌸</emoji>",
    "sparkle": "<emoji id='5325547803936572038'>✨</emoji>",
    "party": "<emoji id='5393313205227366608'>🎉</emoji>",
    "anime": "<emoji id='5303111165365206395'>🎬</emoji>",
    "user": "<emoji id='5373012449597335010'>👤</emoji>",
    "rarity": "<emoji id='6102617459204822706'>🌹</emoji>",
    "coin": "<emoji id='5384490809825450636'>🪙</emoji>",
    "gift": "<emoji id='5384490809825450636'>🎁</emoji>",
    "clock": "<emoji id='6203809036182232315'>⏳</emoji>",
    "check": "<emoji id='6082375377123023700'>✅</emoji>",
    "lock": "<emoji id='5472308992514464048'>🔒</emoji>",
    "wind": "<emoji id='5447644863644320013'>💨</emoji>",
    "error": "<emoji id='5472267631979405211'>🚫</emoji>",
}

def bq(text: str) -> str:
    """Keep the whole response visually grouped as a Telegram blockquote."""
    return f"<blockquote>{text}</blockquote>"

def pe(name: str) -> str:
    return PE.get(name, "✨")

# ---------------- in-memory state ----------------
msg_count: dict = {}      # chat_id -> messages since last spawn
freq_cache: dict = {}     # chat_id -> spawn frequency
spam_state: dict = {}     # chat_id -> (last_user_id, streak)
active: dict = {}         # chat_id -> spawn info
spawning: set = set()     # chats jaha abhi spawn chal raha hai
chat_locks: dict = {}


def _lock(chat_id):
    if chat_id not in chat_locks:
        chat_locks[chat_id] = asyncio.Lock()
    return chat_locks[chat_id]


def rarity_emoji(r: str) -> str:
    return RARITY_EMOJI.get((r or "").lower(), "🌟")


def random_rarity() -> str:
    names = [r[0] for r in RARITIES]
    weights = [r[2] for r in RARITIES]
    return random.choices(names, weights=weights, k=1)[0]


# =====================================================================
#                          API PARSING
# =====================================================================
IMAGE_KEYS = ["image", "img", "image_url", "imageurl", "img_url", "photo", "pic", "picture", "url", "file", "link"]
NAME_KEYS = ["name", "character", "character_name", "charactername", "char_name", "char", "answer", "full_name", "waifu"]
ANIME_KEYS = ["anime", "anime_name", "animename", "series", "source", "from", "show", "title"]
HINT_KEYS = ["caption", "hint", "hidden", "masked", "hidden_name", "masked_name", "question", "text"]
RARITY_KEYS = ["rarity", "rank", "tier"]


def _flatten(data) -> dict:
    """Nested JSON ko flat karo (BFS). Pehla mila hua key jeetega."""
    flat = {}
    queue = [data]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(v, (dict, list)):
                    queue.append(v)
                elif v is not None and str(v).strip():
                    flat.setdefault(str(k).lower(), v)
        elif isinstance(cur, list):
            queue.extend(cur)
    return flat


def _pick(flat: dict, keys: list):
    for k in keys:
        if k in flat:
            return str(flat[k]).strip()
    return None


def parse_api(data) -> dict | None:
    if isinstance(data, list):
        data = data[0] if data else {}
    flat = _flatten(data)

    image = None
    for k in IMAGE_KEYS:
        v = flat.get(k)
        if isinstance(v, str) and (v.startswith("http") or v.startswith("/")):
            image = v
            break
    if not image:  # koi bhi image jaisa URL dhoondo
        for v in flat.values():
            if isinstance(v, str) and re.match(r"^https?://\S+\.(jpe?g|png|webp|gif)(\?\S*)?$", v, re.I):
                image = v
                break
    if image and image.startswith("/"):
        image = urljoin(WAIFU_API, image)

    name = _pick(flat, NAME_KEYS)
    anime = _pick(flat, ANIME_KEYS) or "Unknown"
    hint = _pick(flat, HINT_KEYS)
    rarity = _pick(flat, RARITY_KEYS)

    # kabhi-kabhi "character" ke andar hi image url aa jata hai - usko naam mat samjho
    if name and name.startswith("http"):
        name = None
    if not image or not name:
        return None
    return {"image": image, "name": name, "anime": anime, "hint": hint, "rarity": rarity}


def clean_api_hint(hint) -> str:
    """Remove Telegram/custom HTML emoji markup while retaining its visible fallback text."""
    text = html.unescape(str(hint or "")).strip()
    text = re.sub(
        r"<emoji\b[^>]*>(.*?)</emoji>", r"\1", text, flags=re.IGNORECASE | re.DOTALL
    )
    return re.sub(r"<[^>]+>", "", text).strip()


async def fetch_raw():
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(WAIFU_API) as r:
            ctype = r.headers.get("Content-Type", "")
            body = await r.read()
            return r.status, ctype, body


async def fetch_character() -> dict | None:
    try:
        status, ctype, body = await fetch_raw()
        if status != 200:
            log.warning(f"Waifu API status {status}")
            return None
        if "image" in ctype:
            log.error("Waifu API ne sirf image di, naam nahi mila. /waifuapi se response check karo.")
            return None
        data = json.loads(body.decode("utf-8", "ignore"))
        info = parse_api(data)
        if not info:
            log.error(f"Waifu API response samajh nahi aaya: {str(data)[:300]}")
        return info
    except Exception as e:
        log.error(f"Waifu API error: {e}")
        return None


async def download_image(url: str):
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                data = await r.read()
                if len(data) < 500:
                    return None
                bio = io.BytesIO(data)
                bio.name = "waifu.jpg"
                return bio
    except Exception as e:
        log.warning(f"Waifu image download fail: {e}")
        return None


# =====================================================================
#                      NAME MATCHING / HINT
# =====================================================================
def clean_name(name: str) -> str:
    name = re.sub(r"\(.*?\)|\[.*?\]", " ", name)  # "Rem (Re:Zero)" -> "Rem"
    name = unidecode(name).lower()
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def is_correct(guess: str, answer: str) -> bool:
    g, a = clean_name(guess), clean_name(answer)
    if not g or not a:
        return False
    if g == a:
        return True
    gw, aw = g.split(), a.split()
    if sorted(gw) == sorted(aw):  # "Uchiha Sasuke" == "Sasuke Uchiha"
        return True
    # First name ya last name akela bhi valid guess ho: e.g.
    # "Sakura Kinomoto" ke liye "Sakura" / "Kinomoto" dono accept hon.
    if len(gw) == 1 and len(gw[0]) >= 2 and gw[0] in aw:
        return True
    # Spaces may differ, but unrelated partial/fuzzy guesses accept nahi honge.
    return "".join(gw) == "".join(aw)


def make_hint(name: str) -> str:
    """Har word ka pehla aur aakhri letter dikhao, beech me *  ->  'Hinata Hyuga' = 'H****a H***a'"""
    words = re.sub(r"\(.*?\)|\[.*?\]", "", name).split()
    if not words:
        return "?"

    def mask(w):
        pos = [i for i, ch in enumerate(w) if ch.isalnum()]
        if len(pos) <= 2:  # 'Al' -> 'A*'
            return "".join(ch if i == pos[0] else ("*" if ch.isalnum() else ch) for i, ch in enumerate(w)) if pos else w
        first, last = pos[0], pos[-1]
        return "".join(ch if i in (first, last) or not ch.isalnum() else "*" for i, ch in enumerate(w))

    return " ".join(mask(w) for w in words)


# =====================================================================
#                              SPAWN
# =====================================================================
async def spawn_character(chat_id: int, manual: bool = False) -> bool:
    if chat_id in spawning:
        return False
    spawning.add(chat_id)
    try:
        info = await fetch_character()
        if not info:
            return False

        key = f"{clean_name(info['name'])}|{clean_name(info['anime'])}"
        rarity = (info["rarity"] or random_rarity()).title()
        char = await wdb.get_or_create_character(key, info["name"], info["anime"], rarity)

        photo = await download_image(info["image"]) or char.get("file_id") or info["image"]

        api_hint = clean_api_hint(info["hint"])
        if api_hint and ("\n" in api_hint or len(api_hint) > 60):
            # API ke markup/custom-emoji tags hata kar readable plain text dikhayo.
            body = f"{pe('sparkle')} <b>ʜɪɴᴛ:</b> {html.escape(api_hint)}\n"
        else:
            hint = api_hint or make_hint(char["name"])
            body = (
                f"{pe('anime')} <b>ᴀɴɪᴍᴇ:</b> {html.escape(char['anime'])}\n"
                f"{pe('user')} <b>ɴᴀᴍᴇ:</b> <code>{html.escape(hint)}</code>\n"
            )
        caption = (
            f"{pe('flower')} <b>ɴᴇᴡ ᴡᴀɪғᴜ ᴀᴘᴘᴇᴀʀᴇᴅ!</b>\n\n"
            f"{body}"
            f"{pe('rarity')} {rarity_emoji(char['rarity'])} <b>ʀᴀʀɪᴛʏ:</b> {html.escape(char['rarity'])}\n\n"
            f"{pe('sparkle')} <code>/guess ɴᴀᴍᴇ</code> ʏᴀ ɪs ɪᴍᴀɢᴇ ᴋᴏ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ sᴀʜɪ ɴᴀᴀᴍ ʙʜᴇᴊᴏ."
        )
        caption = bq(caption[:1000])
        previous_message_id = await wdb.get_last_spawn_message(chat_id)
        try:
            sent = await app.send_photo(
                chat_id, photo=photo, caption=caption, has_spoiler=True
            )
        except Exception as e:
            log.warning(f"Waifu spawn send fail in {chat_id}: {e}")
            return False

        if previous_message_id and previous_message_id != sent.id:
            try:
                await app.delete_messages(chat_id, previous_message_id)
            except Exception as e:
                log.debug(f"Previous waifu message delete failed in {chat_id}: {e}")
        await wdb.set_last_spawn_message(chat_id, sent.id)

        if sent.photo:
            await wdb.set_character_file_id(char["_id"], sent.photo.file_id)

        spawn_id = f"{chat_id}:{sent.id}"
        active[chat_id] = {
            "spawn_id": spawn_id,
            "char": char,
            "msg_id": sent.id,
            "time": time.time(),
            "caught_by": None,
        }
        if FLEE_TIME > 0:
            asyncio.create_task(_flee_later(chat_id, spawn_id))
        return True
    finally:
        spawning.discard(chat_id)


async def _flee_later(chat_id: int, spawn_id: str):
    await asyncio.sleep(FLEE_TIME)
    sp = active.get(chat_id)
    if not sp or sp["spawn_id"] != spawn_id or sp["caught_by"]:
        return
    active.pop(chat_id, None)
    c = sp["char"]
    try:
        await app.send_message(
            chat_id,
            f"{pe('wind')} <b>ᴄʜᴀʀᴀᴄᴛᴇʀ ʙʜᴀᴀɢ ɢᴀʏᴀ!</b>\n\n"
            f"ᴠᴏ <b>{html.escape(c['name'])}</b> ᴛʜᴀ, <i>{html.escape(c['anime'])}</i> sᴇ.",
            reply_to_message_id=sp["msg_id"],
        )
    except Exception:
        pass


@app.on_message(
    filters.group & ~filters.bot & ~filters.via_bot & ~filters.service,
    group=77,
)
async def waifu_message_counter(_, message: Message):
    if not message.from_user:
        return
    if message.text and message.text.startswith(("/", "!", ".")):
        return
    chat_id = message.chat.id
    uid = message.from_user.id

    # simple anti-spam: ek hi banda lagatar msg karke spawn na kara paye
    last_uid, streak = spam_state.get(chat_id, (None, 0))
    streak = streak + 1 if last_uid == uid else 1
    spam_state[chat_id] = (uid, streak)
    if streak > SPAM_STREAK:
        return

    if chat_id not in freq_cache:
        freq_cache[chat_id] = await wdb.get_spawn_frequency(chat_id, DEFAULT_FREQ)

    msg_count[chat_id] = msg_count.get(chat_id, 0) + 1
    if msg_count[chat_id] >= freq_cache[chat_id]:
        msg_count[chat_id] = 0
        asyncio.create_task(spawn_character(chat_id))


# =====================================================================
#                              GUESS
# =====================================================================
async def _award_character(message: Message, char: dict, chat_id: int):
    user = message.from_user
    coins = RARITY_COINS.get(char["rarity"].lower(), 10)
    await wdb.add_character_to_user(user.id, user.first_name, char["_id"], coins)
    await wdb.inc_chat_top(chat_id, user.id, user.first_name)
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌸 ʜᴀʀᴇᴍ ᴅᴇᴋʜᴏ", callback_data=f"wf_harem|{user.id}|0")]]
    )
    await message.reply_text(
        bq(f"{pe('party')} {user.mention} ɴᴇ ᴡᴀɪғᴜ ᴄᴀᴛᴄʜ ᴋᴀʀ ʟɪ!\n\n"
        f"{pe('user')} <b>ɴᴀᴍᴇ:</b> {html.escape(char['name'])}\n"
        f"{pe('anime')} <b>ᴀɴɪᴍᴇ:</b> {html.escape(char['anime'])}\n"
        f"{pe('rarity')} {rarity_emoji(char['rarity'])} <b>ʀᴀʀɪᴛʏ:</b> {html.escape(char['rarity'])}\n"
        f"{pe('sparkle')} <b>ɪᴅ:</b> <code>{char['_id']}</code>\n"
        f"{pe('coin')} <b>+{coins} ᴄᴏɪɴs</b>"),
        reply_markup=btn,
    )


async def try_handle_spawn_reply(message: Message) -> bool:
    """Consume replies to the active waifu image, silently ignoring wrong names."""
    replied = message.reply_to_message
    if not message.from_user or not replied or not message.chat:
        return False
    chat_id = message.chat.id
    sp = active.get(chat_id)
    if not sp or replied.id != sp["msg_id"]:
        return False

    guess = (message.text or message.caption or "").strip()
    if not guess:
        return True

    async with _lock(chat_id):
        sp = active.get(chat_id)
        if not sp or replied.id != sp["msg_id"]:
            return False
        if sp["caught_by"]:
            return True
        if FLEE_TIME > 0 and time.time() - sp["time"] > FLEE_TIME:
            active.pop(chat_id, None)
            return True
        char = sp["char"]
        if not is_correct(guess, char["name"]):
            return True
        sp["caught_by"] = message.from_user.mention

    await _award_character(message, char, chat_id)
    return True


@app.on_message(filters.command(["guess", "grab", "catch", "collect"]) & filters.group)
async def guess_cmd(_, message: Message):
    if not message.from_user:
        return
    chat_id = message.chat.id
    if len(message.command) < 2:
        return await message.reply_text("➥ ᴜsᴀɢᴇ : <code>/guess ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴀᴍᴇ</code>")
    guess = message.text.split(maxsplit=1)[1]

    async with _lock(chat_id):
        sp = active.get(chat_id)
        if not sp:
            return await message.reply_text("❌ ᴀʙʜɪ ᴋᴏɪ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴀʜɪ ʜᴀɪ ɪs ɢʀᴏᴜᴘ ᴍᴇ.")
        char = sp["char"]
        if not is_correct(guess, char["name"]):
            return
        if sp["caught_by"]:
            return await message.reply_text(
                f"🔒 ʏᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴘᴇʜʟᴇ ʜɪ {sp['caught_by']} ɴᴇ ᴘᴀᴋᴀᴅ ʟɪʏᴀ!\n"
                f"ᴀɢʟᴇ sᴘᴀᴡɴ ᴋᴀ ᴡᴀɪᴛ ᴋᴀʀᴏ."
            )
        if FLEE_TIME > 0 and time.time() - sp["time"] > FLEE_TIME:
            active.pop(chat_id, None)
            return await message.reply_text("💨 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴘᴇʜʟᴇ ʜɪ ʙʜᴀᴀɢ ᴄʜᴜᴋᴀ ʜᴀɪ.")

        sp["caught_by"] = message.from_user.mention

    await _award_character(message, char, chat_id)


@app.on_message(filters.command("clam"))
async def clam_cmd(_, message: Message):
    if not message.from_user:
        return

    now = int(time.time())
    info = await fetch_character()
    if not info:
        return await message.reply_text("❌ ᴀʙʜɪ ᴡᴀɪғᴜ ɴᴀʜɪ ᴍɪʟ ʀᴀʜɪ, ᴛʜᴏᴅɪ ᴅᴇʀ ʙᴀᴀᴅ ᴛʀʏ ᴋᴀʀᴏ.")

    key = f"{clean_name(info['name'])}|{clean_name(info['anime'])}"
    rarity = (info["rarity"] or random_rarity()).title()
    char = await wdb.get_or_create_character(key, info["name"], info["anime"], rarity)
    if not await wdb.claim_daily_character(
        message.from_user.id, message.from_user.first_name, char["_id"], now
    ):
        user = await wdb.get_user(message.from_user.id)
        last_claim = int(user.get("last_clam_at", now))
        remaining = max(1, 86400 - (now - last_claim))
        hours, minutes = divmod(remaining // 60, 60)
        return await message.reply_text(
            f"⏳ ᴀᴀᴊ ᴋᴀ ᴄʟᴀᴍ ʟᴇ ᴄʜᴜᴋᴇ ʜᴏ. "
            f"{hours}ʜ {minutes}ᴍ ʙᴀᴀᴅ ᴘʜɪʀ ᴄʟᴀɪᴍ ᴋᴀʀ sᴀᴋᴛᴇ ʜᴏ."
        )

    photo = await download_image(info["image"]) or char.get("file_id") or info["image"]
    caption = bq(
        f"{pe('gift')} {message.from_user.mention}, ᴀᴀᴊ ᴋᴀ ᴡᴀɪғᴜ ᴄʟᴀɪᴍ!\n\n"
        f"{pe('user')} <b>ɴᴀᴍᴇ:</b> {html.escape(char['name'])}\n"
        f"{pe('anime')} <b>ᴀɴɪᴍᴇ:</b> {html.escape(char['anime'])}\n"
        f"{pe('rarity')} {rarity_emoji(char['rarity'])} <b>ʀᴀʀɪᴛʏ:</b> {html.escape(char['rarity'])}\n"
        f"{pe('clock')} ᴀɢʟᴀ ᴄʟᴀɪᴍ 24 ɢʜᴀɴᴛᴇ ʙᴀᴀᴅ.")
    try:
        sent = await app.send_photo(
            message.chat.id,
            photo=photo,
            caption=caption,
            has_spoiler=True,
            reply_to_message_id=message.id,
        )
        if sent.photo:
            await wdb.set_character_file_id(char["_id"], sent.photo.file_id)
    except Exception as e:
        log.warning(f"Daily waifu photo send failed for {message.from_user.id}: {e}")
        await message.reply_text(caption)


# =====================================================================
#                              HAREM
# =====================================================================
async def build_harem(user_id: int, page: int, owner_name: str):
    user = await wdb.get_user(user_id)
    ids = user.get("characters", [])
    if not ids:
        return None, None, None

    counts = {}
    for cid in ids:
        counts[cid] = counts.get(cid, 0) + 1
    chars = await wdb.get_characters(list(counts))
    items = sorted(
        [c for c in chars.values()],
        key=lambda c: (c["anime"].lower(), c["name"].lower()),
    )
    total_pages = max(1, (len(items) + HAREM_PER_PAGE - 1) // HAREM_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * HAREM_PER_PAGE:(page + 1) * HAREM_PER_PAGE]

    text = (
        f"{pe('flower')} <b>{html.escape(owner_name)} ᴋᴀ ᴡᴀɪғᴜ ʜᴀʀᴇᴍ</b>\n"
        f"📦 ᴛᴏᴛᴀʟ: <b>{len(ids)}</b> | ᴜɴɪǫᴜᴇ: <b>{len(items)}</b> | 🪙 {user.get('coins', 0)}\n"
        f"📄 ᴘᴀɢᴇ {page + 1}/{total_pages}\n"
    )
    last_anime = None
    for c in chunk:
        if c["anime"] != last_anime:
            text += f"\n{pe('anime')} <b>{html.escape(c['anime'][:40])}</b>\n"
            last_anime = c["anime"]
        mult = f" ×{counts[c['_id']]}" if counts[c["_id"]] > 1 else ""
        text += f"  {rarity_emoji(c['rarity'])} <code>{c['_id']}</code> · {html.escape(c['name'][:30])}{mult}\n"

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"wf_harem|{user_id}|{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"wf_harem|{user_id}|{page + 1}"))
    markup = InlineKeyboardMarkup([nav]) if nav else None

    fav = user.get("fav")
    photo_char = chars.get(fav) if fav in chars else random.choice(items)
    photo = photo_char.get("file_id") if photo_char else None
    return bq(text[:1000]), markup, photo


@app.on_message(filters.command(["harem", "collection", "mywaifu"]))
async def harem_cmd(_, message: Message):
    target = message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else message.from_user
    if not target:
        return
    text, markup, photo = await build_harem(target.id, 0, target.first_name)
    if not text:
        return await message.reply_text("😶 ʜᴀʀᴇᴍ ᴋʜᴀᴀʟɪ ʜᴀɪ! ɢʀᴏᴜᴘ ᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄᴀᴛᴄʜ ᴋᴀʀᴏ.")
    if photo:
        try:
            return await message.reply_photo(photo, caption=text, reply_markup=markup)
        except Exception:
            pass
    await message.reply_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^wf_harem\|"))
async def harem_cb(_, cq: CallbackQuery):
    _, uid, page = cq.data.split("|")
    uid, page = int(uid), int(page)
    if cq.from_user.id != uid:
        return await cq.answer("ʏᴇ ᴛᴜᴍʜᴀʀᴀ ʜᴀʀᴇᴍ ɴᴀʜɪ ʜᴀɪ!", show_alert=True)
    text, markup, _photo = await build_harem(uid, page, cq.from_user.first_name)
    if not text:
        return await cq.answer("ʜᴀʀᴇᴍ ᴋʜᴀᴀʟɪ ʜᴀɪ.", show_alert=True)
    try:
        if cq.message.photo:
            await cq.message.edit_caption(text, reply_markup=markup)
        elif (
            cq.message.from_user
            and cq.message.from_user.is_self
            and cq.message.text
            and "ʜᴀʀᴇᴍ" in cq.message.text
        ):
            await cq.message.edit_text(text, reply_markup=markup)
        else:  # catch message ke button se aaya -> naya message bhejo
            await cq.message.reply_text(text, reply_markup=markup)
    except Exception:
        pass
    await cq.answer()


# =====================================================================
#                        FAV / CHECK / BALANCE
# =====================================================================
def _get_id_arg(message: Message, pos: int = 1):
    try:
        return int(message.command[pos])
    except (IndexError, ValueError):
        return None


@app.on_message(filters.command("fav"))
async def fav_cmd(_, message: Message):
    cid = _get_id_arg(message)
    if cid is None:
        return await message.reply_text("➥ ᴜsᴀɢᴇ : <code>/fav ᴄʜᴀʀᴀᴄᴛᴇʀ_ɪᴅ</code>")
    user = await wdb.get_user(message.from_user.id)
    if cid not in user.get("characters", []):
        return await message.reply_text("❌ ʏᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴛᴜᴍʜᴀʀᴇ ʜᴀʀᴇᴍ ᴍᴇ ɴᴀʜɪ ʜᴀɪ.")
    await wdb.set_fav(message.from_user.id, cid)
    c = await wdb.get_character(cid)
    await message.reply_text(f"💖 <b>{html.escape(c['name'])}</b> ᴀʙ ᴛᴜᴍʜᴀʀɪ ғᴀᴠᴏʀɪᴛᴇ ʜᴀɪ!")


@app.on_message(filters.command(["wcheck", "check"]))
async def check_cmd(_, message: Message):
    cid = _get_id_arg(message)
    if cid is None:
        return await message.reply_text("➥ ᴜsᴀɢᴇ : <code>/wcheck ᴄʜᴀʀᴀᴄᴛᴇʀ_ɪᴅ</code>")
    c = await wdb.get_character(cid)
    if not c:
        return await message.reply_text("❌ ɪs ɪᴅ ᴋᴀ ᴋᴏɪ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴀʜɪ ᴍɪʟᴀ.")
    owners = await wdb.count_character_owners(cid)
    text = (
        f"{pe('user')} <b>ɴᴀᴍᴇ:</b> {html.escape(c['name'])}\n"
        f"{pe('anime')} <b>ᴀɴɪᴍᴇ:</b> {html.escape(c['anime'])}\n"
        f"{pe('rarity')} {rarity_emoji(c['rarity'])} <b>ʀᴀʀɪᴛʏ:</b> {html.escape(c['rarity'])}\n"
        f"🆔 <b>ɪᴅ:</b> <code>{c['_id']}</code>\n"
        f"👥 <b>ᴏᴡɴᴇʀs:</b> {owners}"
    )
    text = bq(text)
    if c.get("file_id"):
        try:
            return await message.reply_photo(c["file_id"], caption=text)
        except Exception:
            pass
    await message.reply_text(text)


@app.on_message(filters.command(["wbalance", "balance", "coins"]))
async def balance_cmd(_, message: Message):
    user = await wdb.get_user(message.from_user.id)
    await message.reply_text(
        f"💰 {message.from_user.mention} ᴋᴇ ᴘᴀᴀs <b>{user.get('coins', 0)}</b> ᴄᴏɪɴs ʜᴀɪɴ\n"
        f"🌸 ᴡᴀɪғᴜs: <b>{len(user.get('characters', []))}</b>"
    )


# =====================================================================
#                           GIFT / TRADE
# =====================================================================
def _target_user(message: Message):
    r = message.reply_to_message
    if not r or not r.from_user or r.from_user.is_bot or r.from_user.id == message.from_user.id:
        return None
    return r.from_user


@app.on_message(filters.command("gift") & filters.group)
async def gift_cmd(_, message: Message):
    target = _target_user(message)
    cid = _get_id_arg(message)
    if not target or cid is None:
        return await message.reply_text("➥ ᴋɪsɪ ᴋᴇ ᴍsɢ ᴘᴇ ʀᴇᴘʟʏ ᴋᴀʀᴏ : <code>/gift ᴄʜᴀʀᴀᴄᴛᴇʀ_ɪᴅ</code>")
    user = await wdb.get_user(message.from_user.id)
    if cid not in user.get("characters", []):
        return await message.reply_text("❌ ʏᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴛᴜᴍʜᴀʀᴇ ᴘᴀᴀs ɴᴀʜɪ ʜᴀɪ.")
    c = await wdb.get_character(cid)
    g, r = message.from_user.id, target.id
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"wf_gift|{g}|{r}|{cid}|y"),
        InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data=f"wf_gift|{g}|{r}|{cid}|n"),
    ]])
    await message.reply_text(
        f"🎁 ᴋʏᴀ ᴛᴜᴍ <b>{html.escape(c['name'])}</b> ᴋᴏ {target.mention} ᴋᴏ ɢɪғᴛ ᴋᴀʀɴᴀ ᴄʜᴀʜᴛᴇ ʜᴏ?",
        reply_markup=btn,
    )


@app.on_callback_query(filters.regex(r"^wf_gift\|"))
async def gift_cb(_, cq: CallbackQuery):
    _, g, r, cid, ans = cq.data.split("|")
    g, r, cid = int(g), int(r), int(cid)
    if cq.from_user.id != g:
        return await cq.answer("ʏᴇ ʙᴜᴛᴛᴏɴ ᴛᴜᴍʜᴀʀᴇ ʟɪʏᴇ ɴᴀʜɪ ʜᴀɪ!", show_alert=True)
    if ans == "n":
        return await cq.message.edit_text("❌ ɢɪғᴛ ᴄᴀɴᴄᴇʟ ʜᴏ ɢᴀʏᴀ.")
    if not await wdb.remove_one_character(g, cid):
        return await cq.message.edit_text("❌ ʏᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀʙ ᴛᴜᴍʜᴀʀᴇ ᴘᴀᴀs ɴᴀʜɪ ʜᴀɪ.")
    try:
        rname = (await app.get_users(r)).first_name
    except Exception:
        rname = str(r)
    await wdb.add_character_to_user(r, rname, cid)
    c = await wdb.get_character(cid)
    await cq.message.edit_text(f"🎁 <b>{html.escape(c['name'])}</b> sᴜᴄᴄᴇssғᴜʟʟʏ ɢɪғᴛ ʜᴏ ɢᴀʏᴀ!")


@app.on_message(filters.command("trade") & filters.group)
async def trade_cmd(_, message: Message):
    target = _target_user(message)
    my_id, their_id = _get_id_arg(message, 1), _get_id_arg(message, 2)
    if not target or my_id is None or their_id is None:
        return await message.reply_text(
            "➥ ᴋɪsɪ ᴋᴇ ᴍsɢ ᴘᴇ ʀᴇᴘʟʏ ᴋᴀʀᴏ : <code>/trade ᴛᴜᴍʜᴀʀᴀ_ɪᴅ ᴜsᴋᴀ_ɪᴅ</code>"
        )
    me = await wdb.get_user(message.from_user.id)
    them = await wdb.get_user(target.id)
    if my_id not in me.get("characters", []):
        return await message.reply_text("❌ ᴘᴇʜʟᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴛᴜᴍʜᴀʀᴇ ᴘᴀᴀs ɴᴀʜɪ ʜᴀɪ.")
    if their_id not in them.get("characters", []):
        return await message.reply_text("❌ ᴅᴜsʀᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴜsᴋᴇ ᴘᴀᴀs ɴᴀʜɪ ʜᴀɪ.")
    a = await wdb.get_character(my_id)
    b = await wdb.get_character(their_id)
    data = f"{message.from_user.id}|{target.id}|{my_id}|{their_id}"
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ᴀᴄᴄᴇᴘᴛ", callback_data=f"wf_trade|{data}|y"),
        InlineKeyboardButton("❌ ʀᴇᴊᴇᴄᴛ", callback_data=f"wf_trade|{data}|n"),
    ]])
    await message.reply_text(
        f"🔄 <b>ᴛʀᴀᴅᴇ ʀᴇǫᴜᴇsᴛ</b>\n\n"
        f"{message.from_user.mention} ᴅᴇɢᴀ : <b>{html.escape(a['name'])}</b>\n"
        f"{target.mention} ᴅᴇɢᴀ : <b>{html.escape(b['name'])}</b>\n\n"
        f"{target.mention}, ᴀᴄᴄᴇᴘᴛ ᴋᴀʀᴏɢᴇ?",
        reply_markup=btn,
    )


@app.on_callback_query(filters.regex(r"^wf_trade\|"))
async def trade_cb(_, cq: CallbackQuery):
    _, a_uid, b_uid, a_cid, b_cid, ans = cq.data.split("|")
    a_uid, b_uid, a_cid, b_cid = int(a_uid), int(b_uid), int(a_cid), int(b_cid)
    if cq.from_user.id not in (a_uid, b_uid):
        return await cq.answer("ʏᴇ ᴛʀᴀᴅᴇ ᴛᴜᴍʜᴀʀᴀ ɴᴀʜɪ ʜᴀɪ!", show_alert=True)
    if ans == "n":
        return await cq.message.edit_text("❌ ᴛʀᴀᴅᴇ ᴄᴀɴᴄᴇʟ ʜᴏ ɢᴀʏᴀ.")
    if cq.from_user.id != b_uid:
        return await cq.answer("sɪʀғ ᴅᴜsʀᴀ ᴜsᴇʀ ᴀᴄᴄᴇᴘᴛ ᴋᴀʀ sᴀᴋᴛᴀ ʜᴀɪ.", show_alert=True)

    if not await wdb.remove_one_character(a_uid, a_cid):
        return await cq.message.edit_text("❌ ᴛʀᴀᴅᴇ ғᴀɪʟ : ᴘᴇʜʟᴇ ᴜsᴇʀ ᴋᴇ ᴘᴀᴀs ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴀʜɪ ʜᴀɪ.")
    if not await wdb.remove_one_character(b_uid, b_cid):
        await wdb.add_character_to_user(a_uid, "", a_cid)  # rollback
        return await cq.message.edit_text("❌ ᴛʀᴀᴅᴇ ғᴀɪʟ : ᴅᴜsʀᴇ ᴜsᴇʀ ᴋᴇ ᴘᴀᴀs ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴀʜɪ ʜᴀɪ.")
    await wdb.add_character_to_user(a_uid, "", b_cid)
    await wdb.add_character_to_user(b_uid, cq.from_user.first_name, a_cid)
    await cq.message.edit_text("✅ ᴛʀᴀᴅᴇ sᴜᴄᴄᴇssғᴜʟ!")


# =====================================================================
#                          LEADERBOARDS
# =====================================================================
MEDALS = ["🥇", "🥈", "🥉"]


@app.on_message(filters.command(["wtop", "top"]))
async def top_cmd(_, message: Message):
    rows = await wdb.top_users(10)
    coins_rows = await wdb.top_by_coins(10)
    if not rows and not coins_rows:
        return await message.reply_text(f"{pe('sparkle')} ᴀʙʜɪ ᴛᴀᴋ ᴋɪsɪ ɴᴇ ᴡᴀɪғᴜ ᴄᴀᴛᴄʜ ɴᴀʜɪ ᴋɪʏᴀ.")
    def board(title, data, field, icon):
        out = f"{icon} <b>{title}</b>\n"
        for i, r in enumerate(data):
            medal = MEDALS[i] if i < 3 else f"<b>{i + 1}.</b>"
            name = html.escape(str(r.get('name') or r['_id'])[:22])
            out += f"{medal} <b>{name}</b> — <code>{int(r.get(field, 0)):,}</code>\n"
        return out
    text = (
        f"{pe('party')} <b>ᴡᴀɪғᴜ ʀᴀɴᴋɪɴɢs</b>\n"
        f"<i>ᴄᴀᴛᴄʜ ᴋᴀʀᴏ • ᴄᴏɪɴs ᴋᴀᴍᴀᴏ • ʀᴀɴᴋ ᴋᴀʀᴏ</i>\n\n"
        f"{board('ᴍᴏsᴛ ᴡᴀɪғᴜ ᴄᴀᴛᴄʜᴇs', rows, 'total', pe('flower'))}\n"
        f"{board('ʀɪᴄʜᴇsᴛ ᴄᴏʟʟᴇᴄᴛᴏʀs', coins_rows, 'coins', pe('coin'))}"
    )
    await message.reply_text(bq(text))


@app.on_message(filters.command("ctop") & filters.group)
async def ctop_cmd(_, message: Message):
    rows = await wdb.chat_top(message.chat.id, 10)
    if not rows:
        return await message.reply_text("ɪs ɢʀᴏᴜᴘ ᴍᴇ ᴀʙʜɪ ᴛᴀᴋ ᴋᴏɪ ᴄᴀᴛᴄʜ ɴᴀʜɪ ʜᴜᴀ.")
    text = f"🏆 <b>{html.escape(message.chat.title or 'ɢʀᴏᴜᴘ')} — ᴛᴏᴘ ᴄᴀᴛᴄʜᴇʀs</b>\n\n"
    for i, r in enumerate(rows):
        m = MEDALS[i] if i < 3 else f"{i + 1}."
        text += f"{m} {html.escape(str(r.get('name') or r['user_id'])[:25])} — <b>{r['count']}</b>\n"
    await message.reply_text(text)


# =====================================================================
#                    ADMIN / SUDO COMMANDS
# =====================================================================
@app.on_message(filters.command("changetime") & filters.group)
async def changetime_cmd(_, message: Message):
    uid = message.from_user.id if message.from_user else None
    is_sudo = uid in SUDOERS
    if not is_sudo:
        try:
            m = await app.get_chat_member(message.chat.id, uid)
            if m.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                return await message.reply_text("❌ sɪʀғ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs ʏᴇ ᴄʜᴀɴɢᴇ ᴋᴀʀ sᴀᴋᴛᴇ ʜᴀɪɴ.")
        except Exception:
            return
    n = _get_id_arg(message)
    current = freq_cache.get(message.chat.id) or await wdb.get_spawn_frequency(message.chat.id, DEFAULT_FREQ)
    if n is None:
        return await message.reply_text(
            f"⏱ ᴀʙʜɪ ʜᴀʀ <b>{current}</b> ᴍᴇssᴀɢᴇs ʙᴀᴀᴅ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀᴀᴛᴀ ʜᴀɪ.\n"
            f"➥ ᴄʜᴀɴɢᴇ : <code>/changetime 100</code>"
        )
    low = 1 if is_sudo else MIN_FREQ
    if n < low or n > 10000:
        return await message.reply_text(f"❌ ᴠᴀʟᴜᴇ {low} sᴇ 10000 ᴋᴇ ʙɪᴄʜ ʜᴏɴɪ ᴄʜᴀʜɪʏᴇ.")
    await wdb.set_spawn_frequency(message.chat.id, n)
    freq_cache[message.chat.id] = n
    msg_count[message.chat.id] = 0
    await message.reply_text(f"✅ ᴀʙ ʜᴀʀ <b>{n}</b> ᴍᴇssᴀɢᴇs ʙᴀᴀᴅ ᴄʜᴀʀᴀᴄᴛᴇʀ sᴘᴀᴡɴ ʜᴏɢᴀ.")


@app.on_message(filters.command(["summon", "wspawn"]) & filters.group & SUDOERS)
async def summon_cmd(_, message: Message):
    ok = await spawn_character(message.chat.id, manual=True)
    if not ok:
        await message.reply_text("❌ sᴘᴀᴡɴ ғᴀɪʟ — ᴀᴘɪ ʀᴇsᴘᴏɴsᴇ ᴄʜᴇᴄᴋ ᴋᴀʀᴏ : /waifuapi")


@app.on_message(filters.command("waifuapi") & SUDOERS)
async def waifuapi_cmd(_, message: Message):
    """API ka raw response dikhata hai - agar parsing me dikkat ho to yahi se pata chalega."""
    try:
        status, ctype, body = await fetch_raw()
    except Exception as e:
        return await message.reply_text(f"❌ API error : <code>{html.escape(str(e))}</code>")
    raw = body.decode("utf-8", "ignore")[:3000] if "image" not in ctype else f"<{len(body)} bytes image>"
    parsed = None
    try:
        parsed = parse_api(json.loads(raw))
    except Exception:
        pass
    await message.reply_text(
        f"<b>sᴛᴀᴛᴜs :</b> {status}\n<b>ᴛʏᴘᴇ :</b> {html.escape(ctype)}\n\n"
        f"<b>ʀᴀᴡ :</b>\n<pre>{html.escape(raw)}</pre>\n\n"
        f"<b>ᴘᴀʀsᴇᴅ :</b>\n<pre>{html.escape(json.dumps(parsed, ensure_ascii=False, indent=1))}</pre>"
    )
