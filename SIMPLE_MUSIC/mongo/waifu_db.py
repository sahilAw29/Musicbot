# -----------------------------------------------
# 🔸 YORU MUSIC BOT Project
# 🔹 Catch-Your-Waifu : database helpers
# -----------------------------------------------
from pymongo import ReturnDocument

from SIMPLE_MUSIC.core.mongo import mongodb

charsdb = mongodb.waifu_characters      # har spawn hua character (id, name, anime, rarity, file_id)
usersdb = mongodb.waifu_users           # user ki collection (harem), fav, coins
groupsdb = mongodb.waifu_groups         # group settings (spawn frequency)
chattopdb = mongodb.waifu_chat_top      # per-group catch count
countersdb = mongodb.waifu_counters     # auto-increment id


# ---------------- characters ----------------
async def _next_char_id() -> int:
    doc = await countersdb.find_one_and_update(
        {"_id": "char_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


async def get_or_create_character(key: str, name: str, anime: str, rarity: str) -> dict:
    """Same character (name+anime) ko hamesha same ID milegi."""
    doc = await charsdb.find_one({"key": key})
    if doc:
        return doc
    cid = await _next_char_id()
    doc = {
        "_id": cid,
        "key": key,
        "name": name,
        "anime": anime,
        "rarity": rarity,
        "file_id": None,
    }
    try:
        await charsdb.insert_one(doc)
    except Exception:
        # race condition: kisi aur ne pehle insert kar diya
        existing = await charsdb.find_one({"key": key})
        if existing:
            return existing
    return doc


async def set_character_file_id(cid: int, file_id: str):
    await charsdb.update_one({"_id": cid}, {"$set": {"file_id": file_id}})


async def get_character(cid: int):
    return await charsdb.find_one({"_id": cid})


async def get_characters(ids: list) -> dict:
    out = {}
    async for c in charsdb.find({"_id": {"$in": list(set(ids))}}):
        out[c["_id"]] = c
    return out


async def count_character_owners(cid: int) -> int:
    return await usersdb.count_documents({"characters": cid})


# ---------------- users ----------------
async def get_user(user_id: int) -> dict:
    doc = await usersdb.find_one({"_id": user_id})
    return doc or {"_id": user_id, "characters": [], "fav": None, "coins": 0}


async def claim_daily_character(user_id: int, name: str, cid: int, claimed_at: int) -> bool:
    """Atomically grant one character if the user's 24-hour cooldown has elapsed."""
    await usersdb.update_one(
        {"_id": user_id},
        {"$setOnInsert": {"name": name, "characters": [], "fav": None, "coins": 0}},
        upsert=True,
    )
    updated = await usersdb.find_one_and_update(
        {
            "_id": user_id,
            "$or": [
                {"last_clam_at": {"$exists": False}},
                {"last_clam_at": {"$lte": claimed_at - 86400}},
            ],
        },
        {
            "$push": {"characters": cid},
            "$set": {"name": name, "last_clam_at": claimed_at},
        },
        return_document=ReturnDocument.AFTER,
    )
    return updated is not None


async def add_character_to_user(user_id: int, name: str, cid: int, coins: int = 0):
    update = {"$push": {"characters": cid}, "$inc": {"coins": coins}}
    if name:  # khaali naam se purana naam overwrite na ho
        update["$set"] = {"name": name}
    await usersdb.update_one({"_id": user_id}, update, upsert=True)


async def remove_one_character(user_id: int, cid: int) -> bool:
    """Sirf ek copy remove karta hai ($pull saari copies hata deta)."""
    user = await usersdb.find_one({"_id": user_id})
    if not user or cid not in user.get("characters", []):
        return False
    chars = list(user["characters"])
    chars.remove(cid)
    update = {"$set": {"characters": chars}}
    if user.get("fav") == cid and cid not in chars:
        update["$set"]["fav"] = None
    await usersdb.update_one({"_id": user_id}, update)
    return True


async def set_fav(user_id: int, cid: int):
    await usersdb.update_one({"_id": user_id}, {"$set": {"fav": cid}}, upsert=True)


async def top_users(limit: int = 10) -> list:
    """Global users with both catch-count and coin totals for /top UI."""
    pipeline = [
        {"$project": {
            "name": 1,
            "total": {"$size": {"$ifNull": ["$characters", []]}},
            "coins": {"$ifNull": ["$coins", 0]},
        }},
        {"$sort": {"total": -1}},
        {"$limit": limit},
    ]
    return [d async for d in usersdb.aggregate(pipeline)]

async def top_by_coins(limit: int = 10) -> list:
    pipeline = [
        {"$project": {
            "name": 1,
            "total": {"$size": {"$ifNull": ["$characters", []]}},
            "coins": {"$ifNull": ["$coins", 0]},
        }},
        {"$sort": {"coins": -1, "total": -1}},
        {"$limit": limit},
    ]
    return [d async for d in usersdb.aggregate(pipeline)]


# ---------------- groups ----------------
async def get_spawn_frequency(chat_id: int, default: int) -> int:
    doc = await groupsdb.find_one({"_id": chat_id})
    return int(doc["freq"]) if doc and doc.get("freq") else default


async def set_spawn_frequency(chat_id: int, freq: int):
    await groupsdb.update_one({"_id": chat_id}, {"$set": {"freq": freq}}, upsert=True)


async def get_last_spawn_message(chat_id: int):
    doc = await groupsdb.find_one({"_id": chat_id}, {"last_spawn_message_id": 1})
    return doc.get("last_spawn_message_id") if doc else None


async def set_last_spawn_message(chat_id: int, message_id: int):
    await groupsdb.update_one(
        {"_id": chat_id},
        {"$set": {"last_spawn_message_id": message_id}},
        upsert=True,
    )


async def inc_chat_top(chat_id: int, user_id: int, name: str):
    await chattopdb.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}, "$set": {"name": name}},
        upsert=True,
    )


async def chat_top(chat_id: int, limit: int = 10) -> list:
    cur = chattopdb.find({"chat_id": chat_id}).sort("count", -1).limit(limit)
    return [d async for d in cur]
