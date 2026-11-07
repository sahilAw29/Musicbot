import os
from typing import List

import yaml

languages = {}
languages_present = {}


def get_string(lang: str):
    return languages[lang]


# Shown in its own blockquote under every "now playing" card.
CARD_CREDIT = (
    "\n<blockquote><b><emoji id='5411125521230620410'>🎁</emoji> Mᴀᴅᴇ Bʏ Hᴇʀ : "
    "<a href=\"https://t.me/flirts_x\">⏤͟͟͞͞𝗦ᴀ𝗛ɪ𝗟</a> "
    "<emoji id='5384488237140057287'>✨</emoji></b></blockquote>"
)

for filename in os.listdir(r"./strings/langs/"):
    if "en" not in languages:
        languages["en"] = yaml.safe_load(
            open(r"./strings/langs/en.yml", encoding="utf8")
        )
        languages_present["en"] = languages["en"]["name"]
    if filename.endswith(".yml"):
        language_name = filename[:-4]
        if language_name == "en":
            continue
        languages[language_name] = yaml.safe_load(
            open(r"./strings/langs/" + filename, encoding="utf8")
        )
        for item in languages["en"]:
            if item not in languages[language_name]:
                languages[language_name][item] = languages["en"][item]
    try:
        languages_present[language_name] = languages[language_name]["name"]
    except:
        print("There is some issue with the language file inside bot.")
        exit()

for strings_of_language in languages.values():
    for card in ("stream_1", "stream_2"):
        strings_of_language[card] += CARD_CREDIT
