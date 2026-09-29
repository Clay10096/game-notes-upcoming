"""Public PlayStation Store category parameters and product-card helpers."""
from __future__ import annotations

import re

from common import SourceError, amount, playstation_url

PS_API = "https://web.np.playstation.com/api/graphql/v1//op"
# Public categoryGridRetrieve persisted operation used by current store pages.
PS_QUERY_HASH = "88c0b9a1273c6d320c51cd73e390924e21ae28bf09f01cde8b84b1034b16cd03"
PS_LOCALES = {"hk": "zh-Hant-HK", "jp": "ja-JP", "us": "en-US"}
PS_PATHS = {"hk": "zh-hant-hk", "jp": "ja-jp", "us": "en-us"}
PS_PREFIXES = {"hk": "HK$", "jp": "¥", "us": "$"}
PS_TYPES = ("FULL_GAME", "GAME_BUNDLE", "PREMIUM_EDITION")


def ps_price(value, region):
    prefix = PS_PREFIXES[region]
    if not isinstance(value, str) or not value.startswith(prefix):
        raise SourceError("Unexpected PlayStation currency")
    text = value[len(prefix):].strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", text):
        raise SourceError("Invalid PlayStation displayed price")
    return amount(text)


def ps_artwork(media):
    if not isinstance(media, list):
        raise SourceError("PlayStation artwork list missing")
    options = {item.get("role"): item.get("url") for item in media
               if isinstance(item, dict) and item.get("type") == "IMAGE"}
    primary = options.get("MASTER") or options.get("GAMEHUB_COVER_ART")
    fallback = options.get("GAMEHUB_COVER_ART") if primary != options.get("GAMEHUB_COVER_ART") else None
    def small(url):
        if not url:
            return None
        playstation_url(url, True)
        return url.split("?", 1)[0] + "?w=160&thumb=false"
    return small(primary), small(fallback)
