# Music bot fixes

This build includes the earlier playback, queue, autoplay, skip, next, shuffle, callback, cookie-based YouTube resolver, welcome, and AI formatting fixes.

## Yoru identity migration

The previous AI module, command registration, legacy backup document, prompts, and user-facing identity have been removed. Yoru is now the single AI identity throughout the project. `/ask`, `/chatgpt`, and `/yoru` use `SIMPLE_MUSIC/plugins/tools/yoru_ai.py`; the old duplicate module is no longer loaded.

Yoru responses and status messages are rendered inside Telegram HTML blockquotes and converted to the requested mini/small-cap style. The bot-added welcome message is `🩷 Wᴇʟᴄᴏᴍᴇ Bᴀʙʏ ꨄ {mention} 🥳`.

## Validation

No legacy AI identity references remain in the project. `python3 -m compileall -q SIMPLE_MUSIC config.py` passes. The uploaded project does not include an automated test suite.
