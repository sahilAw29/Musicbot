# -----------------------------------------------
# Colour + premium emoji wale inline buttons (config.BUTTON_COLOUR / BUTTON_ICON)
# Agar Telegram icon/colour reject kare to simple buttons par fallback.
# -----------------------------------------------
import config
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

BLUE = enums.ButtonStyle.PRIMARY
GREEN = enums.ButtonStyle.SUCCESS
RED = enums.ButtonStyle.DANGER

# Premium (custom) emoji ids — project me pehle se use ho rahe
ICON_CLOSE = "5424756476117807727"
ICON_SPARKLE = "5325547803936572038"  # ✨
ICON_BOT = "5309832892262654231"      # 🤖
ICON_CLIP = "6098158454222887821"     # 📎
ICON_EYES = "5208841018379612211"     # 👀
ICON_CROWN = "5217822164362739968"    # 👑
ICON_OK = "6082375377123023700"       # ✅
ICON_MUSIC = "5258289810082111221"    # 🎵 (owner ne diya)
ICON_MOD = "5258508428212445001"      # 🔨 (owner ne diya)
ICON_BACK = "5258084656674250503"     # ⬅ (owner ne diya)


def pe(icon_id: str, fallback: str) -> str:
    """Message text/caption ke andar premium emoji."""
    return f"<emoji id='{icon_id}'>{fallback}</emoji>"


def btn(text, callback_data=None, url=None, style=None, icon=None):
    kw = {}
    if style is not None and getattr(config, "BUTTON_COLOUR", False):
        kw["style"] = style
    if icon and getattr(config, "BUTTON_ICON", False):
        kw["icon_custom_emoji_id"] = icon
    if url:
        return InlineKeyboardButton(text, url=url, **kw)
    return InlineKeyboardButton(text, callback_data=callback_data, **kw)


def _copy(b, keep_style):
    kw = {}
    style = getattr(b, "style", None)
    if keep_style and style is not None:
        kw["style"] = style
    if b.url:
        return InlineKeyboardButton(b.text, url=b.url, **kw)
    return InlineKeyboardButton(b.text, callback_data=b.callback_data, **kw)


def markup_variants(rows):
    """[full, bina icon (colour rahe), bilkul simple] — jo chal jaye."""
    return [
        InlineKeyboardMarkup(rows),
        InlineKeyboardMarkup([[_copy(b, True) for b in r] for r in rows]),
        InlineKeyboardMarkup([[_copy(b, False) for b in r] for r in rows]),
    ]
