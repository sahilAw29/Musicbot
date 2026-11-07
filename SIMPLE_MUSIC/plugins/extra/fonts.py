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
import re
import unicodedata

from pyrogram import enums, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from SIMPLE_MUSIC.utils.Simple_font import Fonts
from SIMPLE_MUSIC import LOGGER, app
from SIMPLE_MUSIC.utils.fancy_buttons import (
    BLUE, GREEN, RED, ICON_CLOSE, ICON_EYES, ICON_SPARKLE, btn, markup_variants,
)
import config

# ⏤͟͞Nᴀᴢᴀʀɪʏᴀ ꭙ Mᴜꜱɪᴄ wala style
_SMALL = dict(zip(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
))


# Fancy letters ko wapas normal A-Z banane ke liye (koi bhi font likho, stylish ban jaye)
_BACK = {v: k for k, v in _SMALL.items() if v != k}
_BACK.update({"ɢ": "g", "ǫ": "q", "ꜰ": "f", "ꜱ": "s", "ʀ": "r", "ᴀ": "a", "ʏ": "y", "ɴ": "n", "ʟ": "l", "ɪ": "i", "ʜ": "h"})
for _base, _start in ((0x1F150, "A"), (0x1F170, "A"), (0x1F1E6, "A")):  # 🅐 🅰 🇦 wale
    for _i in range(26):
        _BACK[chr(_base + _i)] = chr(ord(_start) + _i)


def _learn_lookalikes():
    """Bot ke apne saare fonts (爪卂几ᘜ卂, ᑕOᗰIᑕ...) ke letters ko wapas A-Z se jodo."""
    for low_up in ("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        for name in dir(Fonts):
            if name.startswith("_"):
                continue
            try:
                fancy = getattr(Fonts, name)(low_up)
            except Exception:
                continue
            if not isinstance(fancy, str) or len(fancy) != 26:
                continue
            for f_ch, p_ch in zip(fancy, low_up):
                if not f_ch.isascii() and f_ch not in _BACK:
                    _BACK[f_ch] = p_ch


_learn_lookalikes()


def _to_plain(text: str) -> str:
    """𝐒𝐀𝐇𝐈𝐋 / Ⓢⓐⓗⓘⓛ / Sᴀʜɪʟ / S̶a̶h̶i̶l̶ → SAHIL / Sahil (normal letters)."""
    text = text.replace("⏤͟͞", "").replace(" ꭙ ", " ").replace("ꭙ", " ")
    text = re.sub(r"(?<=[^\x00-\x7f])\|(?=[^\x00-\x7f])", "i", text)  # manga font ka | = i
    text = unicodedata.normalize("NFKD", text)
    out = []
    for ch in text:
        ch = _BACK.get(ch, ch)
        # Latin letter ke upar lage decoration (̶ ͟ ̾ ͆ etc) hatao — Hindi matras ko mat chhedo
        if unicodedata.category(ch) in ("Mn", "Me") and out and out[-1].isascii():
            continue
        if ch == "\ufe0e":  # Ⓢ︎ jaise font ka text-style mark (emoji ka ️ rehne do)
            continue
        out.append(ch)
    text = unicodedata.normalize("NFKC", "".join(out))
    # 🇸 🇦 🇭 🇮 🇱  🇲 🇺 🇸 🇮 🇨 jaisa (har letter alag, words ke beech 2 space)
    tokens = [t for t in text.split(" ") if t]
    if len(tokens) > 1 and all(len(t) == 1 for t in tokens):
        text = " ".join(w.replace(" ", "") for w in re.split(r" {2,}", text.strip()))
    return text


def nazariya_style(text: str) -> str:
    """Har word ka pehla letter capital, baaki small caps, words ke beech ꭙ.
    Koi bhi font me likha ho (𝐁𝐨𝐥𝐝, Ⓒⓘⓡⓒⓛⓔ, ꜱᴍᴀʟʟ ᴄᴀᴘꜱ...), pehle normal karke phir style lagta hai."""
    text = _to_plain(text)
    out_lines = []
    for line in text.split("\n"):
        words = []
        for word in line.split():
            first, rest = word[0], word[1:]
            words.append(first.upper() + "".join(_SMALL.get(ch, ch) for ch in rest.lower()))
        out_lines.append(" ꭙ ".join(words))
    return "⏤͟͞" + "\n".join(out_lines)


# font wale message ka original text (chat_id, message_id) -> text
_FONT_TEXT = {}


def _colourize(rows):
    """Har font button ko colour + premium emoji do."""
    out = []
    for i, row in enumerate(rows):
        new_row = []
        for j, b in enumerate(row):
            data = b.callback_data or ""
            if data == "style+nazariya":
                new_row.append(btn(b.text, callback_data=data, style=GREEN, icon=ICON_SPARKLE))
            elif data == "close_reply":
                new_row.append(btn(b.text, callback_data=data, style=RED, icon=ICON_CLOSE))
            elif data.startswith("nxt"):
                new_row.append(btn(b.text, callback_data=data, style=GREEN, icon=ICON_EYES))
            else:
                # rows me baari baari blue / green
                new_row.append(btn(b.text, callback_data=data, style=BLUE if (i + j) % 2 == 0 else GREEN))
        out.append(new_row)
    return out


async def _safe_markup(m, rows):
    for markup in markup_variants(rows):  # colour+icon → colour → simple
        try:
            return await m.message.edit_reply_markup(markup)
        except Exception as error:
            if "MESSAGE_NOT_MODIFIED" in str(error):
                return
            LOGGER(__name__).warning(f"/font buttons edit failed: {error}")


def _strip_icons(rows):
    """Custom emoji icon / colour hata ke simple button (kuch accounts par icon allowed nahi)."""
    return [
        [InlineKeyboardButton(b.text, callback_data=b.callback_data) for b in row]
        for row in rows
    ]


async def _original_text(m):
    """Button dabane par original text nikaalo (cache → /font msg → bot msg)."""
    msg = m.message
    key = (msg.chat.id, msg.id)
    if key in _FONT_TEXT:
        return _FONT_TEXT[key]
    src = msg.reply_to_message
    if src is None and getattr(msg, "reply_to_message_id", None):
        try:
            src = await m._client.get_messages(msg.chat.id, msg.reply_to_message_id)
        except Exception:
            src = None
    if src and src.text and len(src.text.split(None, 1)) > 1:
        text = src.text.split(None, 1)[1]
    else:
        text = msg.text or ""
    _FONT_TEXT[key] = text
    return text

def _close_icon():
    if getattr(config, "BUTTON_ICON", False):
        return {"icon_custom_emoji_id": "5424756476117807727"}
    return {}

@app.on_message(filters.command(["font", "fonts"]))
async def style_buttons(c, m, cb=False):
    text = ""
    if not cb:
        parts = (m.text or "").split(None, 1)
        if len(parts) > 1:
            text = parts[1]
        elif m.reply_to_message and (m.reply_to_message.text or m.reply_to_message.caption):
            text = m.reply_to_message.text or m.reply_to_message.caption
        if not text:
            return await m.reply_text("❖ ᴜsᴀɢᴇ : <code>/font Your Text</code>\nʏᴀ ᴋɪsɪ ᴛᴇxᴛ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ /font")
    buttons = [
        [InlineKeyboardButton("⏤͟͞Sᴛʏʟɪꜱʜ ꭙ Fᴏɴᴛ", callback_data="style+nazariya")],
        [
            InlineKeyboardButton("𝚃𝚢𝚙𝚎𝚠𝚛𝚒𝚝𝚎𝚛", callback_data="style+typewriter"),
            InlineKeyboardButton("𝕆𝕦𝕥𝕝𝕚𝕟𝕖", callback_data="style+outline"),
            InlineKeyboardButton("𝐒𝐞𝐫𝐢𝐟", callback_data="style+serif"),
        ],
        [
            InlineKeyboardButton("𝑺𝒆𝒓𝒊𝒇", callback_data="style+bold_cool"),
            InlineKeyboardButton("𝑆𝑒𝑟𝑖𝑓", callback_data="style+cool"),
            InlineKeyboardButton("Sᴍᴀʟʟ Cᴀᴘs", callback_data="style+small_cap"),
        ],
        [
            InlineKeyboardButton("𝓈𝒸𝓇𝒾𝓅𝓉", callback_data="style+script"),
            InlineKeyboardButton("𝓼𝓬𝓻𝓲𝓹𝓽", callback_data="style+script_bolt"),
            InlineKeyboardButton("ᵗⁱⁿʸ", callback_data="style+tiny"),
        ],
        [
            InlineKeyboardButton("ᑕOᗰIᑕ", callback_data="style+comic"),
            InlineKeyboardButton("𝗦𝗮𝗻𝘀", callback_data="style+sans"),
            InlineKeyboardButton("𝙎𝙖𝙣𝙨", callback_data="style+slant_sans"),
        ],
        [
            InlineKeyboardButton("𝘚𝘢𝘯𝘴", callback_data="style+slant"),
            InlineKeyboardButton("𝖲𝖺𝗇𝗌", callback_data="style+sim"),
            InlineKeyboardButton("Ⓒ︎Ⓘ︎Ⓡ︎Ⓒ︎Ⓛ︎Ⓔ︎Ⓢ︎", callback_data="style+circles"),
        ],
        [
            InlineKeyboardButton("🅒︎🅘︎🅡︎🅒︎🅛︎🅔︎🅢︎", callback_data="style+circle_dark"),
            InlineKeyboardButton("𝔊𝔬𝔱𝔥𝔦𝔠", callback_data="style+gothic"),
            InlineKeyboardButton("𝕲𝖔𝖙𝖍𝖎𝖈", callback_data="style+gothic_bolt"),
        ],
        [
            InlineKeyboardButton("C͜͡l͜͡o͜͡u͜͡d͜͡s͜͡", callback_data="style+cloud"),
            InlineKeyboardButton("H̆̈ă̈p̆̈p̆̈y̆̈", callback_data="style+happy"),
            InlineKeyboardButton("S̑̈ȃ̈d̑̈", callback_data="style+sad"),
        ],
        [InlineKeyboardButton ("ᴄʟᴏsᴇ",callback_data="close_reply", **_close_icon()),InlineKeyboardButton ("ɴᴇxᴛ ➻", callback_data="nxt")],
    ]
    if not cb:
        # pehli baar hi ⏤͟͞Nᴀᴍᴇ ꭙ Sᴛʏʟᴇ wala font dikhao
        styled = nazariya_style(text)
        sent, last_error = None, None
        # 1) normal  2) bina custom-emoji icon  3) sabse simple — jo chal jaye
        attempts = [(mk, {"parse_mode": enums.ParseMode.DISABLED}) for mk in markup_variants(_colourize(buttons))]
        attempts.append((attempts[-1][0], {}))
        for markup, extra in attempts:
            try:
                sent = await m.reply_text(styled, reply_markup=markup, **extra)
                break
            except Exception as error:
                last_error = error
                LOGGER(__name__).warning(f"/font send failed: {error}")
        if sent is None:
            return await m.reply_text(f"❖ ғᴏɴᴛ ɴᴀʜɪ ʙᴀɴ ᴘᴀʏᴀ : <code>{last_error}</code>")
        _FONT_TEXT[(sent.chat.id, sent.id)] = text
        if len(_FONT_TEXT) > 2000:  # memory saaf rakho
            for k in list(_FONT_TEXT)[:1000]:
                _FONT_TEXT.pop(k, None)
    else:
        await m.answer()
        await _safe_markup(m, _colourize(buttons))


@app.on_callback_query(filters.regex(r"^nxt"))
async def nxt(c, m):
    if m.data == "nxt":
        buttons = [
            [
                InlineKeyboardButton("🇸 🇵 🇪 🇨 🇮 🇦 🇱 ", callback_data="style+special"),
                InlineKeyboardButton("🅂🅀🅄🄰🅁🄴🅂", callback_data="style+squares"),
                InlineKeyboardButton(
                    "🆂︎🆀︎🆄︎🅰︎🆁︎🅴︎🆂︎", callback_data="style+squares_bold"
                ),
            ],
            [
                InlineKeyboardButton("ꪖꪀᦔꪖꪶꪊᥴ𝓲ꪖ", callback_data="style+andalucia"),
                InlineKeyboardButton("爪卂几ᘜ卂", callback_data="style+manga"),
                InlineKeyboardButton("S̾t̾i̾n̾k̾y̾", callback_data="style+stinky"),
            ],
            [
                InlineKeyboardButton(
                    "B̥ͦu̥ͦb̥ͦb̥ͦl̥ͦe̥ͦs̥ͦ", callback_data="style+bubbles"
                ),
                InlineKeyboardButton(
                    "U͟n͟d͟e͟r͟l͟i͟n͟e͟", callback_data="style+underline"
                ),
                InlineKeyboardButton("꒒ꍏꀷꌩꌃꀎꁅ", callback_data="style+ladybug"),
            ],
            [
                InlineKeyboardButton("R҉a҉y҉s҉", callback_data="style+rays"),
                InlineKeyboardButton("B҈i҈r҈d҈s҈", callback_data="style+birds"),
                InlineKeyboardButton("S̸l̸a̸s̸h̸", callback_data="style+slash"),
            ],
            [
                InlineKeyboardButton("s⃠t⃠o⃠p⃠", callback_data="style+stop"),
                InlineKeyboardButton(
                    "S̺͆k̺͆y̺͆l̺͆i̺͆n̺͆e̺͆", callback_data="style+skyline"
                ),
                InlineKeyboardButton("A͎r͎r͎o͎w͎s͎", callback_data="style+arrows"),
            ],
            [
                InlineKeyboardButton("ዪሀክቿነ", callback_data="style+qvnes"),
                InlineKeyboardButton("S̶t̶r̶i̶k̶e̶", callback_data="style+strike"),
                InlineKeyboardButton("F༙r༙o༙z༙e༙n༙", callback_data="style+frozen"),
            ],
            [InlineKeyboardButton ("ᴄʟᴏsᴇ",callback_data="close_reply", **_close_icon()),InlineKeyboardButton ("ʙᴀᴄᴋ", callback_data="nxt+0")],
        ]
        await m.answer()
        await _safe_markup(m, _colourize(buttons))
    else:
        await style_buttons(c, m, cb=True)


@app.on_callback_query(filters.regex(r"^style\+"))
async def style(c, m):
    try:
        await m.answer()
    except Exception:
        pass
    cmd, style = m.data.split('+', 1)
    cls = None
    if style == "nazariya":
        cls = nazariya_style
    if style == "typewriter":
        cls = Fonts.typewriter
    if style == "outline":
        cls = Fonts.outline
    if style == "serif":
        cls = Fonts.serief
    if style == "bold_cool":
        cls = Fonts.bold_cool
    if style == "cool":
        cls = Fonts.cool
    if style == "small_cap":
        cls = Fonts.smallcap
    if style == "script":
        cls = Fonts.script
    if style == "script_bolt":
        cls = Fonts.bold_script
    if style == "tiny":
        cls = Fonts.tiny
    if style == "comic":
        cls = Fonts.comic
    if style == "sans":
        cls = Fonts.san
    if style == "slant_sans":
        cls = Fonts.slant_san
    if style == "slant":
        cls = Fonts.slant
    if style == "sim":
        cls = Fonts.sim
    if style == "circles":
        cls = Fonts.circles
    if style == "circle_dark":
        cls = Fonts.dark_circle
    if style == "gothic":
        cls = Fonts.gothic
    if style == "gothic_bolt":
        cls = Fonts.bold_gothic
    if style == "cloud":
        cls = Fonts.cloud
    if style == "happy":
        cls = Fonts.happy
    if style == "sad":
        cls = Fonts.sad
    if style == "special":
        cls = Fonts.special
    if style == "squares":
        cls = Fonts.square
    if style == "squares_bold":
        cls = Fonts.dark_square
    if style == "andalucia":
        cls = Fonts.andalucia
    if style == "manga":
        cls = Fonts.manga
    if style == "stinky":
        cls = Fonts.stinky
    if style == "bubbles":
        cls = Fonts.bubbles
    if style == "underline":
        cls = Fonts.underline
    if style == "ladybug":
        cls = Fonts.ladybug
    if style == "rays":
        cls = Fonts.rays
    if style == "birds":
        cls = Fonts.birds
    if style == "slash":
        cls = Fonts.slash
    if style == "stop":
        cls = Fonts.stop
    if style == "skyline":
        cls = Fonts.skyline
    if style == "arrows":
        cls = Fonts.arrows
    if style == "qvnes":
        cls = Fonts.rvnes
    if style == "strike":
        cls = Fonts.strike
    if style == "frozen":
        cls = Fonts.frozen
    if cls is None:
        return
    original = await _original_text(m)
    if not original:
        return
    try:
        new_text = cls(original)
    except Exception:
        return
    current = m.message.reply_markup
    options = [current]
    if current and getattr(current, "inline_keyboard", None):
        options += markup_variants(_colourize(current.inline_keyboard))
    for markup in options:
        try:
            await m.message.edit_text(new_text, reply_markup=markup, parse_mode=enums.ParseMode.DISABLED)
            break
        except Exception as error:
            if "MESSAGE_NOT_MODIFIED" in str(error):
                break


__help__ = """

 ❍ /fonts <text> *:* ᴄᴏɴᴠᴇʀᴛs sɪᴍᴩʟᴇ ᴛᴇxᴛ ᴛᴏ ʙᴇᴀᴜᴛɪғᴜʟ ᴛᴇxᴛ ʙʏ ᴄʜᴀɴɢɪɴɢ ɪᴛ's ғᴏɴᴛ.
 """

__mod_name__ = "Fᴏɴᴛ"