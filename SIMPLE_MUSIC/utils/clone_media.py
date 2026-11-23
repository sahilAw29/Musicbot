# -----------------------------------------------
# Clone bots ke liye saved media (photo / video / gif / sticker).
#
# Telegram ka file_id sirf usi bot me chalta hai jisne use banaya.
# Isliye:
#  • Main bot apne saare saved media (start videos, /admin panel ki photos,
#    welcome video, loading sticker, .env ke file_id) disk par clone_media/
#    me rakhta hai — save hote hi + har 2 min me check.
#  • Clone bot jab bhi main bot ka file_id bhejne ki koshish kare, wo apne aap
#    disk wali copy upload karta hai (sirf pehli baar), phir apna file_id
#    yaad rakhta hai. Code me kahin aur kuch badalna nahi padta.
# -----------------------------------------------
import asyncio
import hashlib
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEDIA_DIR = os.path.join(ROOT_DIR, "clone_media")

_CLONE_IDS = {}       # main bot file_id -> clone bot ka apna file_id
_export_lock = None


def _dir(file_id: str) -> str:
    return os.path.join(MEDIA_DIR, hashlib.sha1(str(file_id).encode()).hexdigest()[:20])


def _looks_like_file_id(value) -> bool:
    if not isinstance(value, str) or len(value) < 20 or " " in value:
        return False
    if value.startswith(("http://", "https://", "/", "./")) or os.path.exists(value):
        return False
    return file_kind(value) is not None


def file_kind(file_id: str):
    try:
        from pyrogram.file_id import FileId
        return FileId.decode(str(file_id)).file_type.name.lower()
    except Exception:
        return None


def local_media(file_id: str):
    """Disk par rakhi copy ka path, ya None."""
    d = _dir(file_id)
    if not os.path.isdir(d):
        return None
    for name in os.listdir(d):
        path = os.path.join(d, name)
        if os.path.isfile(path) and os.path.getsize(path) > 0 and not name.endswith(".part"):
            return path
    return None


# ───────────────────── main bot: media disk par rakho ─────────────────────
async def _collect_ids():
    import config
    ids = set()
    for value in vars(config).values():
        if _looks_like_file_id(value):
            ids.add(value)
    try:
        from SIMPLE_MUSIC.utils.dynamic_settings import MEDIA_SETTINGS
        for key, (_, _, default) in MEDIA_SETTINGS.items():
            for value in (getattr(config, key, None), default):
                if _looks_like_file_id(value):
                    ids.add(value)
    except Exception:
        pass
    try:
        from SIMPLE_MUSIC.utils.start_videos_db import startvideosdb
        async for doc in startvideosdb.find({}):
            if _looks_like_file_id(doc.get("media")):
                ids.add(doc["media"])
    except Exception:
        pass
    return ids


async def export_media():
    """Jo media abhi disk par nahi hai, use download karo. (sirf main bot)"""
    global _export_lock
    if _export_lock is None:
        _export_lock = asyncio.Lock()
    if _export_lock.locked():
        return
    async with _export_lock:
        from SIMPLE_MUSIC import LOGGER, app
        os.makedirs(MEDIA_DIR, exist_ok=True)
        for fid in await _collect_ids():
            if local_media(fid):
                continue
            d = _dir(fid)
            os.makedirs(d, exist_ok=True)
            try:
                await app.download_media(fid, file_name=d + "/")
            except Exception as e:
                LOGGER(__name__).warning(f"clone media download failed ({file_kind(fid)}): {e}")


def trigger_export():
    """Kuch naya save hua → background me export (clone process me kuch nahi karta)."""
    import config
    if getattr(config, "IS_CLONE_BOT", False):
        return
    try:
        asyncio.get_event_loop().create_task(export_media())
    except Exception:
        pass


# ───────────────────── clone bot: main ke file_id ko apna banao ─────────────────────
_SEND_METHODS = {
    "send_photo": "photo",
    "send_video": "video",
    "send_animation": "animation",
    "send_sticker": "sticker",
    "send_document": "document",
    "send_audio": "audio",
    "send_voice": "voice",
    "send_video_note": "video_note",
}


def _new_file_id(sent, field):
    obj = getattr(sent, field, None)
    if obj is None and field == "photo":
        obj = getattr(sent, "photo", None)
    return getattr(obj, "file_id", None)


def _wrap_send(fn, field):
    async def wrapper(*args, **kwargs):
        if field in kwargs:
            original = kwargs[field]
            setter = lambda v: kwargs.__setitem__(field, v)
        elif len(args) >= 2:
            args = list(args)
            original = args[1]
            setter = lambda v: args.__setitem__(1, v)
        else:
            return await fn(*args, **kwargs)
        if not _looks_like_file_id(original):
            return await fn(*args, **kwargs)
        mine = _CLONE_IDS.get(original)
        if mine:
            setter(mine)
            try:
                return await fn(*args, **kwargs)
            except Exception:
                _CLONE_IDS.pop(original, None)
        path = local_media(original)
        if not path:
            setter(original)
            return await fn(*args, **kwargs)
        setter(path)
        sent = await fn(*args, **kwargs)
        new_id = _new_file_id(sent, field)
        if new_id:
            _CLONE_IDS[original] = new_id
        return sent
    return wrapper


def _wrap_edit_media(fn):
    async def wrapper(*args, **kwargs):
        media = kwargs.get("media") if "media" in kwargs else (args[2] if len(args) >= 3 else None)
        original = getattr(media, "media", None)
        if media is not None and _looks_like_file_id(original):
            mine = _CLONE_IDS.get(original)
            path = mine or local_media(original)
            if path:
                media.media = path
                sent = await fn(*args, **kwargs)
                if not mine:
                    kind = type(media).__name__.replace("InputMedia", "").lower()
                    field = {"photo": "photo", "video": "video", "animation": "animation",
                             "document": "document", "audio": "audio"}.get(kind)
                    new_id = _new_file_id(sent, field) if field and hasattr(sent, field) else None
                    if new_id:
                        _CLONE_IDS[original] = new_id
                return sent
        return await fn(*args, **kwargs)
    return wrapper


def install_clone_patches(client):
    """Clone bot ke client par lagao: main bot ke file_id apne aap kaam karenge."""
    for name, field in _SEND_METHODS.items():
        fn = getattr(client, name, None)
        if fn:
            setattr(client, name, _wrap_send(fn, field))
    fn = getattr(client, "edit_message_media", None)
    if fn:
        setattr(client, "edit_message_media", _wrap_edit_media(fn))


async def clone_sync_loop():
    """Clone bot: main bot me jo naya save ho (start videos, /admin settings) wo yahan bhi aaye."""
    while True:
        await asyncio.sleep(60)
        try:
            import SIMPLE_MUSIC.utils.start_videos_db as sv
            sv._cache = None
            from SIMPLE_MUSIC.utils.dynamic_settings import load_overrides
            await load_overrides()
        except Exception:
            pass


async def main_export_loop():
    """Main bot: har 2 min me naya saved media disk par."""
    while True:
        try:
            await export_media()
        except Exception:
            pass
        await asyncio.sleep(120)
