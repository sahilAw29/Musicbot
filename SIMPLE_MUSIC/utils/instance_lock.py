# -----------------------------------------------
# Ek bot sirf EK jagah chale.
#
# Agar wahi bot (same token) pehle se kahin aur chal raha hai (dusra VPS,
# Railway ka purana deploy, ya galti se 2 baar `bash start`), to ye naya
# process wait karega — saath me chalne se Telegram session band kar deta hai
# (AUTH_KEY_DUPLICATED) aur clones do baar start hote hain.
#
# Lock MongoDB me hai, har 20 sec heartbeat. Purana process band hua to
# 60 sec ke andar naya process khud chalu ho jata hai.
# -----------------------------------------------
import asyncio
import os
import socket
import time
import uuid

import config

INSTANCE = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
STALE_AFTER = 60
BEAT_EVERY = 20


def _key():
    token = getattr(config, "BOT_TOKEN", "") or ""
    return "bot:" + token.split(":")[0]


def _col():
    from SIMPLE_MUSIC.core.mongo import mongodb
    return mongodb.instance_locks


async def acquire(log):
    from pymongo.errors import DuplicateKeyError
    key = _key()
    warned = False
    while True:
        now = time.time()
        try:
            await _col().update_one(
                {"_id": key, "$or": [{"ts": {"$lt": now - STALE_AFTER}}, {"owner": INSTANCE}]},
                {"$set": {"owner": INSTANCE, "ts": now}},
                upsert=True,
            )
            if warned:
                log.info("Purana process band ho gaya, ab ye chalu ho raha hai.")
            asyncio.get_event_loop().create_task(_heartbeat(log))
            return
        except DuplicateKeyError:
            if not warned:
                doc = await _col().find_one({"_id": key}) or {}
                log.warning(
                    f"Ye bot pehle se dusri jagah chal raha hai ({doc.get('owner')}). "
                    f"Dono saath chale to session band ho jata hai, isliye wait kar raha hoon. "
                    f"Purana band karo (pkill -f SIMPLE_MUSIC / purana deploy), ye khud chalu ho jayega."
                )
                warned = True
            await asyncio.sleep(15)


async def _heartbeat(log):
    while True:
        await asyncio.sleep(BEAT_EVERY)
        try:
            r = await _col().update_one(
                {"_id": _key(), "owner": INSTANCE}, {"$set": {"ts": time.time()}}
            )
            if r.matched_count == 0:
                log.error("Lock kisi aur process ne le liya — ye process band ho raha hai (double chalne se bachne ke liye).")
                os._exit(1)
        except Exception:
            pass  # Mongo thodi der na mile to bhi chalte raho


async def release():
    try:
        await _col().delete_one({"_id": _key(), "owner": INSTANCE})
    except Exception:
        pass
