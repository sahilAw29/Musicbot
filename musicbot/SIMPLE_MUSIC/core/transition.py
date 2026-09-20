"""Concurrency helpers for voice-chat queue transitions."""

from functools import wraps


def _chat_id_from_call(args, kwargs):
    chat_id = kwargs.get("chat_id")
    if chat_id is not None:
        return int(chat_id)

    # The command handler receives chat_id as its fourth positional argument.
    if len(args) > 3 and isinstance(args[3], int):
        return args[3]

    # Callback handlers carry the target chat in callback data (e.g.
    # ``ADMIN Skip|-100123``).  This also covers the autoplay skip button.
    for arg in args:
        data = getattr(arg, "data", None)
        if not data:
            continue
        try:
            return int(str(data).rsplit("|", 1)[-1].split()[-1])
        except (TypeError, ValueError, IndexError):
            continue
    return None


def stream_transition(func):
    """Serialize a complete queue/voice transition for one chat.

    Stream-ended updates and user skip callbacks can arrive concurrently. The
    lock is deliberately held across the queue mutation and replacement stream
    startup, so a late update cannot consume the newly selected track.
    """
    @wraps(func)
    async def locked(*args, **kwargs):
        chat_id = _chat_id_from_call(args, kwargs)
        owner = args[0] if args else None
        if owner is not None and chat_id is not None and hasattr(owner, "_get_transition_lock"):
            lock_owner = owner
        elif chat_id is not None:
            # Pyrogram handlers receive the client as their first argument;
            # the Call singleton owns the locks, not that client instance.
            from SIMPLE_MUSIC.core.call import SIMPLE
            lock_owner = SIMPLE
        else:
            lock_owner = None
        if lock_owner is not None and chat_id is not None:
            async with lock_owner._get_transition_lock(chat_id):
                return await func(*args, **kwargs)
        return await func(*args, **kwargs)

    return locked
