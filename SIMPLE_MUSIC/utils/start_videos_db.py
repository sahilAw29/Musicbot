# -----------------------------------------------
# /start random video system
# Owner/sudo /addvideo se jitne chahe video add kar sakte hain.
# Har /start par inme se ek random video bheja jata hai.
# Koi video add nahi hai to config.START_IMG_URL use hota hai.
# -----------------------------------------------
import random
import time

import config
from SIMPLE_MUSIC.core.mongo import mongodb

startvideosdb = mongodb.start_videos

_cache = None  # list of video docs, None = abhi load nahi hua
_last_key = None  # pichli baar bheja gaya video (same video dobara na aaye)


async def get_start_videos() -> list:
    global _cache
    if _cache is None:
        _cache = [doc async for doc in startvideosdb.find({}).sort("added_on", 1)]
    return _cache


async def add_start_video(key: str, media: str, kind: str, added_by: int) -> bool:
    """True = naya add hua, False = pehle se tha."""
    global _cache
    if await startvideosdb.find_one({"_id": key}):
        return False
    doc = {
        "_id": key,
        "media": media,
        "type": kind,  # "video" / "animation" / "url"
        "added_by": added_by,
        "added_on": time.time(),
    }
    await startvideosdb.insert_one(doc)
    _cache = None
    return True


async def delete_start_video(key: str) -> bool:
    global _cache
    result = await startvideosdb.delete_one({"_id": key})
    _cache = None
    return result.deleted_count > 0


async def clear_start_videos() -> int:
    global _cache
    result = await startvideosdb.delete_many({})
    _cache = None
    return result.deleted_count


async def random_start_media():
    """Random video doc lo; koi video nahi hai to START_IMG_URL (string) lo."""
    global _last_key
    videos = await get_start_videos()
    if not videos:
        return config.START_IMG_URL
    choices = [v for v in videos if v["_id"] != _last_key] or videos
    picked = random.choice(choices)
    _last_key = picked["_id"]
    return picked
