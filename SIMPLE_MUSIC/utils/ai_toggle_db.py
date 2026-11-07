# -----------------------------------------------
# /ai on | /ai off — reply-chat AI ko chat wise on/off karna
# Default: ON. Jis chat me /ai off kiya, uska id yahan save hota hai.
# -----------------------------------------------
from SIMPLE_MUSIC.core.mongo import mongodb

aioffdb = mongodb.ai_off_chats
_off_cache = None  # set of chat_ids


async def _load():
    global _off_cache
    if _off_cache is None:
        _off_cache = {doc["_id"] async for doc in aioffdb.find({})}
    return _off_cache


async def is_ai_on(chat_id: int) -> bool:
    return chat_id not in await _load()


async def set_ai(chat_id: int, on: bool):
    cache = await _load()
    if on:
        cache.discard(chat_id)
        await aioffdb.delete_one({"_id": chat_id})
    else:
        cache.add(chat_id)
        await aioffdb.update_one({"_id": chat_id}, {"$set": {"_id": chat_id}}, upsert=True)
